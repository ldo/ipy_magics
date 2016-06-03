#+
# Cell magic for IPython that allow the inclusion of RenderMan code.
# The graphical rendered output will be displayed in the notebook.
#
# Copyright 2016 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import os
import re
import subprocess
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
    def run_aqsis(input, timeout = None, debug = False) :

        outfile = None
        did_ribfile = False
        was_shader_file = False

        def open_ribfile() :
            nonlocal outfile, did_ribfile
            assert outfile == None
            if did_ribfile :
                raise RuntimeError("all .rib output must be together")
            #end if
            outfile = open(ribfile_name, "w")
            outfile.write("Display \"%(outfile)s\" \"file\" \"rgba\"\n" % {"outfile" : imgfile_name})
            was_shader_file = False
            did_ribfile = True
        #end open_ribfile

    #begin run_aqsis
        png_data = None # to begin with
        temp_dir = tempfile.mkdtemp(prefix = "rman-magic-")
        try :
            keep_temps = debug
            work_dir = os.path.join(temp_dir, "work")
            os.mkdir(work_dir)
              # separate subdirectory for files created by caller
            ribfile_name = os.path.join(temp_dir, "in.rib")
            imgfile_name = os.path.join(temp_dir, "out.tif")
              # pity Aqsis cannot generate PNG directly...
            submagic_pat = re.compile(r"^\%(\w+)(?:\s+(.+))?$")
            display_pat = re.compile(r"^\s*display\s*[\"\s]", flags = re.IGNORECASE)
            params_pat = re.compile(r"\s+")
            input_line = iter(input.split("\n"))
            include_stack = []
            linenr = 0
            while True :
                while True :
                    line = next(input_line, None)
                    if line != None :
                        if len(include_stack) == 0 :
                            linenr += 1
                        #end if
                        break
                    #end if
                    if len(include_stack) == 0 :
                        break
                    input_line = include_stack.pop()
                #end while
                if line == None or len(include_stack) == 0 and line.startswith("%") :
                    if line != None :
                        parse = submagic_pat.match(line)
                        if parse == None or len(parse.groups()) != 2 :
                            raise SyntaxError("bad directive line", ("<cell input>", linenr, None, line))
                        #end if
                        directive, line_rest = parse.groups()
                        if line_rest != None :
                            line_rest = params_pat.split(line_rest)
                        else :
                            line_rest = []
                        #end if
                    else :
                        directive = None
                    #end if
                    if directive == "include" :
                        if len(line_rest) != 1 :
                            raise SyntaxError("wrong nr args for “include” directive", ("<cell input>", linenr, None, None))
                        #end if
                        include_stack.append(input_line)
                        input_line = iter(open(line_rest[0], "r").read().split("\n"))
                    elif directive in (None, "rib", "sl") :
                        if outfile != None :
                            outfile.close()
                        #end if
                        outfile = None
                        if was_shader_file :
                            # compile shader
                            subprocess.check_call \
                              (
                                args = ("aqsl", shader_filename),
                                cwd = work_dir,
                                timeout = timeout
                              )
                        #end if
                        if line == None :
                            break
                        if directive == "rib" :
                            if len(line_rest) != 0 :
                                raise SyntaxError("unexpected args for “rib” directive", ("<cell input>", linenr, None, None))
                            #end if
                            open_ribfile()
                        elif directive == "sl" :
                            if len(line_rest) != 1 :
                                raise SyntaxError("wrong nr args for “sl” directive", ("<cell input>", linenr, None, None))
                            #end if
                            shader_filename = line_rest[0]
                            if "/" in shader_filename :
                                raise SyntaxError("no slashes allowed in “sl” pathname", ("<cell input>", linenr, None, None))
                            #end if
                            shader_filename += ".sl"
                            outfilename = os.path.join(work_dir, shader_filename)
                            if os.path.exists(outfilename) :
                                raise RuntimeError("shader file “%s” already exists" % shader_filename)
                            #end if
                            outfile = open(outfilename, "w")
                            was_shader_file = True
                        #end if
                    else :
                        raise NameError("unrecognized submagic directive “%s”" % directive)
                    #end if
                    line = None # already processed
                #end if
                if line != None :
                    if outfile == None :
                        open_ribfile()
                    #end if
                    if display_pat.match(line) != None :
                        raise SyntaxError("“display” directive not allowed", ("<cell input>", linenr, None, None))
                    #end if
                    outfile.write(line)
                    outfile.write("\n")
                #end if
            #end while
            aqsis_output = subprocess.check_output \
              (
                args = ("aqsis", ribfile_name),
                stdin = subprocess.DEVNULL,
                stderr = subprocess.STDOUT,
                universal_newlines = True,
                cwd = work_dir,
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
    @magicargs.argument("--debug", help = "whether to keep temp files for debugging (default is false)")
    @magicargs.argument("--timeout", help = "how many seconds to wait for execution completion, defaults to infinite")
    def rman(self, line, cell) :
        "executes the cell contents as RenderMan, and displays returned graphical output."
        args = magicargs.parse_argstring(RManMagic.rman, line)
        timeout = getattr(args, "timeout", None)
        if timeout != None :
            timeout = float(timeout)
        #end if
        debug = getattr(args, "debug", "")[0] in "yYtT1"
        image = self.run_aqsis(input = cell, timeout = timeout, debug = debug)
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
