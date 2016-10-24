#+
# Cell magic for IPython that allows the inclusion of Csound code
# <http://www.csounds.com/>. The audio will be played by the notebook
# server.
#
# Copyright 2016 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import os
import subprocess
import tempfile
import shutil
import shlex
import getopt
import select
import fcntl
import re
from markdown import \
    markdown # from separate python3-markdown package
from IPython.display import \
    Audio
from IPython.core import \
    magic
import IPython.core.magic_arguments as \
    magicargs

@magic.magics_class
class CsoundMagic(magic.Magics) :
    "defines cell magic for executing a Csound orchestra+score and playing back" \
    " the output audio."

    @magic.cell_magic
    def csound(self, line, cell) :
        "executes the cell contents as a Csound “unified” file (both orchestra and" \
        " score definitions in one file)."
        debug = False
        opts, args = getopt.getopt \
          (
            shlex.split(line),
            "",
            ("debug",)
          )
        if len(args) != 0 :
            raise getopt.GetoptError("unexpected args")
        #end if
        for keyword, value in opts :
            if keyword == "--debug" :
                debug = True
            #end if
        #end for
        temp_dir = tempfile.mkdtemp(prefix = "csound-magic-")
        try :
            keep_temps = debug
            cs_file_name = os.path.join(temp_dir, "in.csd")
            sound_file_name = os.path.join(temp_dir, "out.wav")
            cs_file = open(cs_file_name, "w")
            cs_file.write(cell)
            cs_file.close()
            output = subprocess.check_output \
              (
                args = ("csound", "--wave", "-o", sound_file_name, cs_file_name),
                stdin = subprocess.DEVNULL,
                stderr = subprocess.STDOUT,
                universal_newlines = True,
              )
            print(output)
            result = Audio(data = open(sound_file_name, "rb").read())
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
            result
    #end csound

#end CsoundMagic

if __name__ == "__main__" :
    get_ipython().register_magics(CsoundMagic)
#end if
