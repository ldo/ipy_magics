#+
# Cell magic for IPython that allow the inclusion of RenderMan code.
# The graphical rendered output will be displayed in the notebook.
#
# Copyright 2016 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import sys # debug
import os
import subprocess
import select
import fcntl
import tempfile
import shutil
from IPython.display import \
    display_png
from IPython.core import \
    magic
import IPython.core.magic_arguments as \
    magicargs

@magic.magics_class
class RManMagic(magic.Magics) :
    "defines cell magic for executing RenderMan code using Aqsis and displaying" \
    " the output."

    @staticmethod
    def run_aqsis(input, timeout = None) :
        png_data = None # to begin with
        temp_dir = tempfile.mkdtemp(prefix = "rman-magic-")
        try :
            keep_temps = False # debug
            ribfile_name = os.path.join(temp_dir, "in.rib")
            imgfile_name = os.path.join(temp_dir, "out.tif")
              # pity Aqsis cannot generate PNG directly...
            ribfile = open(ribfile_name, "w")
            ribfile.write("Display \"%(outfile)s\" \"file\" \"rgba\"\n" % {"outfile" : imgfile_name})
            ribfile.write(input)
            ribfile.close()
            del ribfile
            aqsis_output = subprocess.check_output \
              (
                args = ("aqsis", ribfile_name),
                stdin = subprocess.DEVNULL,
                stderr = subprocess.STDOUT,
                universal_newlines = True,
                timeout = timeout
              )
            png_data = subprocess.check_output \
              (
                args = ("convert", imgfile_name, "png:/dev/stdout"),
                universal_newlines = False,
                timeout = timeout
              )
        finally :
            if not keep_temps :
                try :
                    shutil.rmtree(temp_dir)
                except OSError :
                    pass
                #end try
            #end if
        #end try
        return \
            png_data
    #end run_aqsis

    # Note on args to actual magic methods:
    #“line” is whatever was typed on the %% line after the magic name.
    #“cell” is the rest of the cell contents.

    @magic.cell_magic
    @magicargs.magic_arguments()
    @magicargs.argument("--timeout", help = "how many seconds to wait for execution completion, defaults to infinite")
    def rman(self, line, cell) :
        "executes the cell contents as RenderMan, and displays returned graphical output."
        args = magicargs.parse_argstring(RManMagic.rman, line)
        timeout = getattr(args, "timeout", None)
        if timeout != None :
            timeout = float(timeout)
        #end if
        image = self.run_aqsis(input = cell, timeout = timeout)
        result = None
        if len(image) != 0 :
            display_png(image, raw = True)
        else :
            result = "No output!"
        #end if
        return \
            result
    #end rman

#end RManMagic

if __name__ == "__main__" :
    get_ipython().register_magics(RManMagic)
#end if
