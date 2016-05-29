#+
# Cell magics for IPython that allow the inclusion of PostScript code.
# The code can produce either textual or graphical output for display
# in the notebook.
#-

import os
import subprocess
import select
import fcntl
from IPython.display import \
    display_pdf, \
    display_png
from IPython.core import \
    magic
import IPython.core.magic_arguments as \
    magicargs

@magic.magics_class
class PSMagics(magic.Magics) :
    "defines cell magics for executing PostScript code using Ghostscript and displaying" \
    " the output:\n" \
    " %%pstext -- displays returned output as text.\n" \
    " %%psgraf -- displays returned output as a graphic.\n" \
    " %%pspdf -- displays returned output as one or more PDF pages."

    @staticmethod
    def run_gs(input, output_format = "png16m", pixel_density = None, papersize = None) :
        # internal routine handling common part of Ghostscript invocation.
        if not isinstance(input, bytes) :
            input = input.encode()
        #end if
        from_child_binary, to_parent_binary = os.pipe()
        for fd in (to_parent_binary,) :
            fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.fcntl(fd, fcntl.F_GETFD) & ~fcntl.FD_CLOEXEC)
        #end for
        args = \
          (
            "gs", "-q", "-dBATCH", "-dNOPAUSE",
              # -dBATCH needed to turn off prompt (doc says -dNOPAUSE does this, but it
              # lies).
            "-sDEVICE=%s" % output_format,
            "-sOutputFile=/dev/fd/%d" % to_parent_binary,
              # separate channel from stdout for returning output graphics
          )
        if pixel_density != None :
            args += \
                (
                        "-r%(pixel_density)ux%(pixel_density)u"
                    %
                        {"pixel_density" : int(pixel_density)},
                )
        #end if
        if papersize != None :
            args += ("-sPAPERSIZE=%s" % papersize,)
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
            pass_fds = (to_parent_binary,),
            close_fds = True # make sure no superfluous references to pipes
          )
        os.close(to_parent_binary)
          # so I get EOF indication on receiving end when child process exits
        to_child_text = proc_gs.stdin.fileno()
        from_child_text = proc_gs.stdout.fileno()
        output = {"text" : b"", "binary" : b""}
        to_read = 1024 # arbitrary
        if len(input) == 0 :
            os.close(to_child_text)
        #end if
        while True :
            did_something = False
            readable, writeable, _ = select.select \
              (
                (from_child_text, from_child_binary), # readable
                ((), (to_child_text,))[len(input) != 0], # writable
                (), # except
                0.01 # timeout
              )
            if to_child_text in writeable :
                nrbytes = os.write(to_child_text, input)
                if nrbytes != 0 :
                    did_something = True
                #end if
                input = input[nrbytes:]
                if len(input) == 0 :
                    os.close(to_child_text)
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
                        bytes_read = os.read(from_child, to_read)
                        output[chan] += bytes_read
                        if len(bytes_read) != 0 :
                            did_something = True
                        #end if
                        if len(bytes_read) < to_read :
                            break
                    #end while
                #end if
            #end for
            if not did_something and proc_gs.poll() != None :
                break
        #end while
        if proc_gs.returncode != 0 :
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
    #“cell” is the rest of the cell contents."

    @magic.cell_magic
    def pstext(self, line, cell) :
        "executes the cell contents as PostScript, and displays returned text output."
        return \
            self.run_gs(cell)[0]
    #end pstext

    @magic.cell_magic
    @magicargs.magic_arguments()
    @magicargs.argument("-r", "--resolution", help = "output dpi, default = 72")
    @magicargs.argument("--papersize", help = "paper size, e.g. a4")
      # see /usr/share/ghostscript/*/Resource/Init/gs_statd.ps for valid paper sizes
    def psgraf(self, line, cell) :
        "executes the cell contents as PostScript, and displays the returned graphic."
        args = magicargs.parse_argstring(PSMagics.psgraf, line)
        display_png \
          (
            self.run_gs
              (
                input = cell,
                pixel_density = getattr(args, "resolution", None),
                papersize = getattr(args, "papersize", None),
              )[1],
            raw = True
          )
    #end psgraf

    @magic.cell_magic
    @magicargs.magic_arguments()
    @magicargs.argument("--papersize", help = "paper size, e.g. a4")
      # see /usr/share/ghostscript/*/Resource/Init/gs_statd.ps for valid paper sizes
    def pspdf(self, line, cell) :
        "executes the cell contents as PostScript, and displays the returned pages" \
        " as a PDF stream."
        args = magicargs.parse_argstring(PSMagics.pspdf, line)
        display_pdf \
          (
            self.run_gs
              (
                input = cell,
                output_format = "pdfwrite",
                papersize = getattr(args, "papersize", None),
              )[1],
            raw = True
          )
    #end pspdf

#end PSMagics

if __name__ == "__main__" :
    get_ipython().register_magics(PSMagics)
#end if
