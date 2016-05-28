#+
# Cell magics for IPython that allow the inclusion of PostScript code.
# The code can produce either textual or graphical output for display
# in the notebook.
#-

import subprocess
from IPython.display import \
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
    " %%psgraf -- displays returned output as a graphic."

    @staticmethod
    def run_gs(input, binary, pixel_density = None, papersize = None) :
      # internal routine handling common part of Ghostscript invocation.
        args = \
          (
            "gs", "-q", "-dBATCH", "-dNOPAUSE",
              # -dBATCH needed to turn off prompt (doc says -dNOPAUSE does this, but it
              # lies).
            "-sDEVICE=png16m", "-sOutputFile=/dev/stdout",
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
            universal_newlines = not binary,
            close_fds = True # make sure no superfluous references to pipes
          )
        stdout, stderr = proc_gs.communicate(input = input)
        status = proc_gs.wait()
        if status != 0 :
            if False :
                raise subprocess.CalledProcessError(cmd = "gs", returncode = status)
            else :
                if binary :
                    stdout = stdout.decode()
                #end if
                raise RuntimeError("gs command returned %s" % stdout)
            #end if
        #end if
        return \
            stdout
    #end run_gs

    # Note on args to actual magic methods:
    #“line” is whatever was typed on the %% line after the magic name.
    #“cell” is the rest of the cell contents."

    @magic.cell_magic
    def pstext(self, line, cell) :
        "executes the cell contents as PostScript, and displays returned text output."
        return \
            self.run_gs(cell, False)
    #end pstext

    @magic.cell_magic
    @magicargs.magic_arguments()
    @magicargs.argument("-r", "--resolution", help = "output dpi, default = 72")
    @magicargs.argument("--papersize", help = "paper size, e.g. a4")
      # see /usr/share/ghostscript/9.19/Resource/Init/gs_statd.ps
    def psgraf(self, line, cell) :
        "executes the cell contents as PostScript, and displays the returned graphic."
        args = magicargs.parse_argstring(PSMagics.psgraf, line)
        display_png \
          (
            self.run_gs
              (
                input = cell.encode(),
                binary = True,
                pixel_density = getattr(args, "resolution", None),
                papersize = getattr(args, "papersize", None),
              ),
            raw = True
          )
    #end psgraf

#end PSMagics

get_ipython().register_magics(PSMagics)
