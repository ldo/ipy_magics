#+
# Cell magic for IPython that allows the assignment of lots of text
# to a Python variable.
#
# Copyright 2016 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import shlex
import getopt # can’t figure out magic.Magics.parse_options
from IPython.core import \
    magic
import IPython.core.magic_arguments as \
    magicargs

@magic.magics_class
class SetVarMagic(magic.Magics) :
    "defines cell magic for defining a Python variable."

    @magic.cell_magic
    def setvar(self, line, cell) :
        "Usage:\n" \
        "\n" \
        "    %%setvar [--split=lines] «varname»\n" \
        "    ... «varvalue» ...\n" \
        "\n" \
        "assigns the remainder of the cell contents as the value of the global variable" \
        " «varname», either as a single string or (if “--split=lines” is specified) a" \
        " list of lines."
        opts, args = getopt.getopt \
          (
            shlex.split(line),
            "",
            ("split=",)
          )
        if len(args) != 1 :
            raise SyntaxError \
              (
                "need exactly one arg, the variable name",
                ("<cell input>", 1, None, line)
              )
        #end if
        varname = args[0]
        varvalue = cell
        for keyword, value in opts :
            if keyword == "--split" :
                if value == "lines" :
                    varvalue = varvalue.split("\n")
                else :
                    raise SyntaxError \
                      (
                        "option for --split can only be lines",
                        ("<cell input>", 1, None, line)
                      )
                #end if
            #end if
        #end for
        get_ipython().push({varname : varvalue})
    #end setvar

#end SetVarMagic

if __name__ == "__main__" :
    get_ipython().register_magics(SetVarMagic)
#end if
