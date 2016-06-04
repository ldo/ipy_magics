#+
# Cell magic for IPython that allows the inclusion of PostScript code.
# The code can produce either textual or graphical output, or both,
# for display in the notebook.
#
# Copyright 2016 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import os
import subprocess
import select
import fcntl
import re
from markdown import \
    markdown # from separate python3-markdown package
from IPython.display import \
    display_pdf, \
    display_png, \
    HTML
from IPython.core import \
    magic
import IPython.core.magic_arguments as \
    magicargs

@magic.magics_class
class PSMagic(magic.Magics) :
    "defines cell magic for executing PostScript code using Ghostscript and displaying" \
    " the output."

    @staticmethod
    def run_gs(input, graphics_format, timeout = None, pixel_density = None, papersize = None) :
        # internal routine handling common part of Ghostscript invocation.
        if not isinstance(input, bytes) :
            input = input.encode()
        #end if
        from_child_binary, to_parent_binary = os.pipe()
        for fd in (to_parent_binary,) :
            fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.fcntl(fd, fcntl.F_GETFD) & ~fcntl.FD_CLOEXEC)
        #end for
        # wrap fds in file objects so Python will automatically close them for me
        from_child_binary = open(from_child_binary, "rb", buffering = 0)
        to_parent_binary = open(to_parent_binary, "wb", buffering = 0)
        args = \
          (
            "gs", "-q", "-dBATCH", "-dNOPROMPT",
            "-sDEVICE=%s" % graphics_format,
            "-sOutputFile=/dev/fd/%d" % to_parent_binary.fileno(),
              # separate channel from stdout for returning output graphics
          )
        prelude = ""
        if pixel_density != None :
            args += \
                (
                        "-r%(pixel_density)ux%(pixel_density)u"
                    %
                        {"pixel_density" : int(pixel_density)},
                )
        #end if
        if papersize != None :
            dimensions_match = re.match(r"^(\d+)[x×\:](\d+)$", papersize)
            if dimensions_match != None :
                prelude += \
                    (
                        "<</PageSize [%(width)u %(height)u] /ImagingBBox null>> setpagedevice\n"
                    %
                        {
                            "width" : float(dimensions_match.group(1)),
                            "height" : float(dimensions_match.group(2)),
                        }
                    )
            else :
                args += ("-sPAPERSIZE=%s" % papersize,)
            #end if
        #end if
        proc_gs = subprocess.Popen \
          (
            args =
                    args
                +
                    (
                        "/dev/stdin",
                          # Side effect of -dBATCH is that gs no longer automatically reads from
                          # stdin, need to specify explicit input filenames.
                    ),
            stdin = subprocess.PIPE,
            stdout = subprocess.PIPE,
            #stderr = subprocess.PIPE, # Ghostscript returns traceback in stdout
            universal_newlines = False, # can’t use this
            pass_fds = (to_parent_binary.fileno(),),
            close_fds = True # make sure no superfluous references to pipes
          )
        to_parent_binary.close()
          # so I get EOF indication on receiving end when child process exits
        to_child_text = proc_gs.stdin
        from_child_text = proc_gs.stdout
        output = {"text" : b"", "binary" : b""}
        to_read = 1024 # arbitrary
        input = prelude.encode() + input
        if len(input) == 0 :
            to_child_text.close()
        #end if
        while True :
            did_something = False
            readable, writeable, _ = select.select \
              (
                (from_child_text, from_child_binary), # readable
                ((), (to_child_text,))[len(input) != 0], # writable
                (), # except
                timeout # timeout
              )
            if to_child_text in writeable :
                nrbytes = os.write(to_child_text.fileno(), input)
                if nrbytes != 0 :
                    did_something = True
                #end if
                input = input[nrbytes:]
                if len(input) == 0 :
                    to_child_text.close()
                #end if
            #end if
            for chan, from_child in \
              (
                ("text", from_child_text),
                ("binary", from_child_binary),
              ) \
            :
                if from_child in readable :
                    while True :
                        bytes_read = os.read(from_child.fileno(), to_read)
                        output[chan] += bytes_read
                        if len(bytes_read) != 0 :
                            did_something = True
                        #end if
                        if len(bytes_read) < to_read :
                            break
                    #end while
                #end if
            #end for
            if not did_something :
                if proc_gs.poll() != None :
                    break
                proc_gs.terminate()
                  # fixme: should also proc_gs.wait()
                raise TimeoutError("Ghostscript is taking too long to respond")
            #end if
        #end while
        from_child_binary.close()
        if proc_gs.returncode != 0 :
            proc_gs.kill()
            proc_gs.stdout.close() # doesn’t happen by default, for some reason
            proc_gs.stdin.close() # might as well, just in case
            if False :
                raise subprocess.CalledProcessError(cmd = "gs", returncode = proc_gs.returncode)
            else :
                raise RuntimeError("gs command returned %s" % output["text"].decode())
            #end if
        #end if
        return \
            output["text"].decode(), output["binary"]
    #end run_gs

    # Note on args to actual magic methods:
    #“line” is whatever was typed on the %% line after the magic name.
    #“cell” is the rest of the cell contents.

    @magic.cell_magic
    @magicargs.magic_arguments()
    @magicargs.argument("--dpi", help = "output dpi, default = 72")
    @magicargs.argument("--graphics", help = "graphical output format, PNG or PDF, defaults to PNG")
    @magicargs.argument("--papersize", help = "paper size, e.g. “a4” or «width»x«height»")
      # see /usr/share/ghostscript/*/Resource/Init/gs_statd.ps for valid predefined paper sizes
    @magicargs.argument("--text", help = "text output format, plain, markdown or HTML, defaults to plain")
    @magicargs.argument("--timeout", help = "how many seconds to wait for execution completion, defaults to infinite")
    def ps(self, line, cell) :
        "executes the cell contents as PostScript, and displays returned text or graphical output."
        args = magicargs.parse_argstring(PSMagic.ps, line)
        graphics_format = getattr(args, "graphics", None)
        if graphics_format != None :
            graphics_format = graphics_format.lower()
        else :
            graphics_format = "png"
        #end if
        text_format = getattr(args, "text", None)
        if text_format != None :
            text_format = text_format.lower()
        else :
            text_format = "plain"
        #end if
        timeout = getattr(args, "timeout", None)
        if timeout != None :
            timeout = float(timeout)
        #end if
        result_text, result_binary = self.run_gs \
          (
            input = cell,
            timeout = timeout,
            graphics_format = {"png" : "png16m", "pdf" : "pdfwrite"}[graphics_format],
            pixel_density = getattr(args, "dpi", None),
            papersize = getattr(args, "papersize", None),
          )
        if len(result_binary) != 0 :
            {"png" : display_png, "pdf" : display_pdf}[graphics_format](result_binary, raw = True)
        #end if
        if len(result_text) != 0 :
            result_text = \
                {
                    "plain" : lambda t : t,
                    "markdown" : lambda t : HTML(markdown(t, extensions = ["tables"])),
                      # contrary to the docs
                      # <http://ipython.readthedocs.io/en/stable/api/generated/IPython.display.html>,
                      # IPython doesn’t provide a display_markdown call (at least not on Debian),
                      # so I have to make my own
                    "html" : HTML,
                }[text_format](result_text)
        else :
            result_text = None # don’t display empty string
        #end if
        return \
            result_text
    #end ps

#end PSMagic

if __name__ == "__main__" :
    get_ipython().register_magics(PSMagic)
#end if
