#+
# Cell magic for IPython that allows the inclusion of RenderMan code.
# The graphical rendered output will be displayed in the notebook.
#
# Copyright 2016 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import enum
import os
import re
import subprocess
import tempfile
import shutil
import shlex
import getopt
from IPython.display import \
    display_png
from IPython.core import \
    magic

@magic.magics_class
class RManMagic(magic.Magics) :
    "defines cell magic for executing RenderMan code using Aqsis and displaying" \
    " the output."

    @staticmethod
    def run_aqsis(input, timeout = None, debug = False, include_search = None, aqsis_opts = None) :

        linenr = None
        line = None
        work_dir = None

        @enum.unique
        class FILE_TYPE(enum.Enum) :
            RIB = 1
            SHADER = 2
        #end FILE_TYPE

        def syntax_error(reason) :
            raise SyntaxError(reason, ("<cell input>", linenr, None, line))
        #end syntax_error

        def compile_rib(filename) :
            extra = []
            if aqsis_opts != None :
                for keyword, value in aqsis_opts :
                    if value != None :
                        extra.append("-%s=%s" % (keyword, value))
                    else :
                        extra.append("-%s" % keyword)
                    #end if
                #end for
            #end if
            aqsis_output = subprocess.check_output \
              (
                args = ["aqsis"] + extra + [filename],
                stdin = subprocess.DEVNULL,
                stderr = subprocess.STDOUT,
                universal_newlines = True,
                cwd = work_dir,
                timeout = timeout
              )
            print(aqsis_output) # debug
        #end compile_rib

        def compile_shader(filename) :
            subprocess.check_call \
              (
                args = ("aqsl", filename),
                cwd = work_dir,
                timeout = timeout
              )
        #end compile_shader

        outfile_actions = \
            {
                FILE_TYPE.RIB : compile_rib,
                FILE_TYPE.SHADER : compile_shader,
            }

    #begin run_aqsis
        png_data = None # to begin with
        temp_dir = tempfile.mkdtemp(prefix = "rman-magic-")
        try :
            keep_temps = debug
            work_dir = os.path.join(temp_dir, "work")
            os.mkdir(work_dir)
              # separate subdirectory for files created by caller
            ribfile_nr = 0
            imgfile_name = os.path.join(temp_dir, "out.tif")
              # pity Aqsis cannot generate PNG directly...
            outfile = None
            outfile_name = None
            outfile_type = None
            did_final_output = False
            submagic_pat = re.compile(r"^\%(\w+)(?:\s+(.+))?$")
            display_pat = re.compile(r"^\s*display\s*(.+)$", flags = re.IGNORECASE)
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
                            syntax_error("bad directive line")
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
                    replace_line = None # initial assumption
                    if directive == "display" :
                        if did_final_output :
                            syntax_error("only one %display directive allowed")
                        #end if
                        if outfile != None and outfile_type != FILE_TYPE.RIB :
                            syntax_error("%display must be in %rib file")
                        #end if
                        replace_line = \
                            (
                                "Display \"%(outfile)s\" \"file\" \"rgba\""
                            %
                                {"outfile" : imgfile_name}
                            )
                        did_final_output = True
                    elif directive == "include" :
                        if len(line_rest) != 1 :
                            syntax_error("wrong nr args for “include” directive")
                        #end if
                        file_arg = line_rest[0]
                        if not file_arg.startswith("/") and include_search != None :
                            try_path = []
                            for try_dir in include_search.split(":") :
                                if try_dir == "&" :
                                    try_path.append(file_arg)
                                else :
                                    try_path.append(os.path.join(try_dir, file_arg))
                                #end if
                            #end for
                        else :
                            try_path = [file_arg]
                        #end if
                        while True :
                            if len(try_path) == 0 :
                                syntax_error("cannot find %include file")
                            #end if
                            file_arg = try_path.pop(0)
                            if os.path.isfile(file_arg) :
                                include_stack.append(input_line)
                                input_line = iter(open(file_arg, "r").read().split("\n"))
                                break
                            #end if
                        #end while
                    elif directive in (None, "rib", "sl") :
                        if outfile != None :
                            outfile.close()
                            outfile = None
                            outfile_actions[outfile_type](outfile_name)
                        #end if
                        if line == None :
                            break
                        if directive == "rib" :
                            if len(line_rest) != 0 :
                                syntax_error("unexpected args for “rib” directive")
                            #end if
                            if did_final_output :
                                syntax_error("no ribs allowed after rib that used “%display”")
                            #end if
                            ribfile_nr += 1
                            outfile_name = os.path.join(temp_dir, "in%03d.rib" % ribfile_nr)
                            outfile = open(outfile_name, "w")
                            outfile_type = FILE_TYPE.RIB
                        elif directive == "sl" :
                            if len(line_rest) != 1 :
                                syntax_error("wrong nr args for “sl” directive")
                            #end if
                            shader_filename = line_rest[0]
                            if "/" in shader_filename :
                                syntax_error("no slashes allowed in “sl” pathname")
                            #end if
                            shader_filename += ".sl"
                            outfile_name = os.path.join(work_dir, shader_filename)
                            if os.path.exists(outfile_name) :
                                syntax_error("shader file “%s” already exists" % shader_filename)
                            #end if
                            outfile = open(outfile_name, "w")
                            outfile_type = FILE_TYPE.SHADER
                        #end if
                    else :
                        syntax_error("unrecognized submagic directive “%s”" % directive)
                    #end if
                    line = replace_line # already processed
                #end if
                if line != None :
                    display_match = display_pat.match(line)
                    if display_match != None :
                        display_parms = shlex.split(display_match.group(1))
                        if len(display_parms) > 2 and display_parms[1].lower() == "framebuffer" :
                            # fixme: perhaps display this image as cell output as well?
                            line = None
                        #end if
                    #end if
                #end if
                if line != None :
                    if outfile == None :
                        ribfile_nr += 1
                        outfile_name = os.path.join(temp_dir, "in%03d.rib" % ribfile_nr)
                        outfile = open(outfile_name, "w")
                        outfile_type = FILE_TYPE.RIB
                    #end if
                    outfile.write(line)
                    outfile.write("\n")
                #end if
            #end while
            if not did_final_output :
                syntax_error("never saw %display directive, no final output produced")
            #end if
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
    def rman(self, line, cell) :
        "executes the cell contents as RenderMan, and displays returned graphical output." \
        "Usage:\n" \
        "\n" \
        "    %%rman «options...»\n" \
        "\n" \
        "where valid options are\n" \
        "    --archive-search=«dir» optional directory to search for .rib files\n" \
        "    --debug keeps temp files for debugging\n" \
        "    --include-search=«dir» optional directories to search for %include files\n" \
        "    --search=«dir» optional directories to search for all files\n" \
        "    --shader-search=«dir» optional directories to search for .sl files\n" \
        "    --texture-search=«dir» optional directories to search for texture files\n" \
        "    --timeout=«timeout» specifies how many seconds to wait for" \
            " subprocesses to respond (default is infinite)\n" \
        "    --verbose=«verbosity» verbosity level 0-3, default is 1"
        timeout = None
        debug = False
        include_search = None
        map_aqsis_opts = \
            {
                "archive-search" : ("archives", True),
              # I don’t think I need “displays”
                "shader-search" : ("shaders", True),
                "procedural-search" : ("procedurals", True),
                "texture-search" : ("textures", True),
                "progress" : ("Progress", False),
                "verbose" : ("verbose", True),
            }
        opts, args = getopt.getopt \
          (
            shlex.split(line),
            "",
                ("debug", "include-search=", "search=", "timeout=",)
            +
                tuple(k + ("", "=")[map_aqsis_opts[k][1]] for k in map_aqsis_opts)
          )
        if len(args) != 0 :
            raise getopt.GetoptError("unexpected args")
        #end if
        aqsis_opts = []
        for keyword, value in opts :
            if keyword == "--debug" :
                debug = True
            elif keyword == "--include-search" :
                include_search = value
            elif keyword == "--search" :
                include_search = value
                for k in ("archives", "shaders", "procedurals", "textures") :
                    aqsis_opts.append((k, value))
                #end for
            elif keyword == "--timeout" :
                timeout = float(value)
            elif keyword.startswith("--") and keyword[2:] in map_aqsis_opts :
                mapname, has_value = map_aqsis_opts[keyword[2:]]
                aqsis_opts.append((mapname, (None, value)[has_value]))
            #end if
        #end for
        image = self.run_aqsis \
          (
            input = cell,
            timeout = timeout,
            debug = debug,
            include_search = include_search,
            aqsis_opts = aqsis_opts
          )
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
