#+
# Cell magic for IPython that allows the inclusion of RenderMan code.
# The graphical rendered output will be displayed in the notebook.
#
# Copyright 2016, 2017 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import enum
import os
import array
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
    def run_aqsis(input, timeout = None, debug = False, source_search = None, aqsis_opts = None) :

        linenr = None
        line = None
        temp_dir = None
        work_dir = None

        def find_file(filename, search_type, must_exist = True) :
            file_arg = filename
            if not file_arg.startswith("/") :
                if search_type == "sources" :
                    search1 = source_search
                elif aqsis_opts != None :
                    search1 = aqsis_opts.get(search_type)
                else :
                    search1 = None
                #end if
                search2 = aqsis_opts.get("resources")
                try_path = []
                for search in (search1, search2) :
                    if search != None :
                        for try_dir in search.split(":") :
                            if try_dir == "&" :
                                try_path.append(os.path.join(work_dir, file_arg))
                            else :
                                try_path.append(os.path.join(try_dir, file_arg))
                            #end if
                        #end for
                    #end if
                #end for
                if len(try_path) == 0 :
                    try_path = [os.path.join(work_dir, file_arg)]
                #end if
            else :
                try_path = [os.path.join(work_dir, file_arg)]
            #end if
            while True :
                if len(try_path) == 0 :
                    if must_exist :
                        syntax_error("cannot find file “%s”" % filename)
                    #end if
                    file_arg = None
                    break
                #end if
                file_arg = try_path.pop(0)
                if os.path.exists(file_arg) :
                    break
                #end if
            #end while
            return \
                file_arg
        #end find_file

        @enum.unique
        class FILE_TYPE(enum.Enum) :
            RIB = 1
            SHADER = 2
        #end FILE_TYPE

        def syntax_error(reason) :
            raise SyntaxError(reason, ("<cell input>", linenr, None, line))
        #end syntax_error

        imgfile_names = None
        images = []

        def collect_display(filename) :
            images.append \
              (
                subprocess.check_output
                  (
                    args = ("convert", filename, "png:/dev/stdout"),
                    universal_newlines = False,
                    timeout = timeout
                  )
              )
        #end collect_display

        def compile_rib(filename) :
            nonlocal imgfile_names
            extra = []
            if aqsis_opts != None :
                for keyword, value in aqsis_opts.items() :
                    if keyword == "resources" :
                        # strange there is no specific command-line option for this
                        assert value != None
                        extra.append("-option=Option \"searchpath\" \"resource \" [\"%s\"]" % value)
                    else :
                        if value != None :
                            extra.append("-%s=%s" % (keyword, value))
                        else :
                            extra.append("-%s" % keyword)
                        #end if
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
            if imgfile_names != None :
                for imgfile_name in imgfile_names :
                    collect_display(imgfile_name)
                #end for
                imgfile_names = None
            #end if
        #end compile_rib

        def compile_shader(filename) :
            slproc = subprocess.Popen \
              (
                args = ("aqsl", filename),
                stdin = subprocess.DEVNULL,
                stdout = subprocess.PIPE,
                stderr = subprocess.STDOUT,
                universal_newlines = True,
                cwd = work_dir
              )
            slproc_output, _ = slproc.communicate(timeout = timeout)
            if slproc_output != None :
                print(slproc_output) # debug
            #end if
            if slproc.returncode != 0 :
                print("compilation of shader “%s” returned %d" % (filename, slproc.returncode))
            #end if
        #end compile_shader

        outfile_actions = \
            {
                FILE_TYPE.RIB : compile_rib,
                FILE_TYPE.SHADER : compile_shader,
            }

        texfile_nr = 0
        ribfile_nr = 0
        imgfile_nr = 0
        outfile = None
        outfile_name = None
        outfile_type = None

        def new_texfile_name() :
            # pity Aqsis cannot accept PNG directly...
            nonlocal texfile_nr
            texfile_nr += 1
            texfile_name = os.path.join(temp_dir, "tex%03d.tif" % texfile_nr)
            return \
                texfile_name
        #end new_texfile_name

        def new_rib_file() :
            # starts writing a new .rib file into outfile.
            nonlocal ribfile_nr, outfile, outfile_name, outfile_type, imgfile_names
            assert outfile == None
            ribfile_nr += 1
            outfile_name = os.path.join(temp_dir, "in%03d.rib" % ribfile_nr)
            outfile = open(outfile_name, "w")
            outfile_type = FILE_TYPE.RIB
            imgfile_names = []
        #end new_rib_file

        def new_imgfile_name() :
            # pity Aqsis cannot generate PNG directly...
            nonlocal imgfile_nr
            imgfile_nr += 1
            imgfile_name = os.path.join(temp_dir, "out%03d.tif" % imgfile_nr)
            imgfile_names.append(imgfile_name)
            return \
                imgfile_name
        #end new_imgfile_name

        display_pat = re.compile(r"^\s*display\s*(.+)$", flags = re.IGNORECASE)
        readarchive_pat = re.compile(r"^\s*readarchive\s*(.+)$", flags = re.IGNORECASE)

        class InputStack :

            def __init__(self) :
                self.include_stack = []
                self.cur_input = None
            #end __init__

            def push_iter(self, lines_iter) :
                if self.cur_input != None :
                    self.include_stack.append(self.cur_input)
                #end if
                self.cur_input = iter(lines_iter)
            #end push_iter

            def push_file(self, filename) :
                self.push_iter(open(filename, "r").read().split("\n"))
            #end push_file

            def __iter__(self) :
                return \
                    self
            #end __iter__

            def __next__(self) :
                assert self.cur_input != None
                while True :
                    line = next(self.cur_input, None)
                    if line != None :
                        break
                    if len(self.include_stack) == 0 :
                        self.cur_input = None
                        raise StopIteration
                    #end if
                    self.cur_input = self.include_stack.pop()
                #end while
                return \
                    line
            #end __next__

            @property
            def include_depth(self) :
                return \
                    len(self.include_stack)
            #end include_depth

        #end InputStack

        cur_input = None
        orig_line = None
        replace_line = None

        def do_include(file_arg, search_type) :
            file_name = find_file(file_arg, search_type)
            cur_input.push_file(file_name)
        #end do_include

        def try_parse_display_line(line) :
            # tries to recognize line as a “display” command, returning the
            # list of params if it is one, None if not.
            display_match = display_pat.match(line)
            if display_match != None :
                display_parms = shlex.split(display_match.group(1))
            else :
                display_parms = None
            #end if
            return \
                display_parms
        #end try_parse_display_line

        def do_auto_display(force_auto) :
            # collects output filenames for automatic display.
            nonlocal line
            display_parms = try_parse_display_line(line)
            if (
                    display_parms != None
                and
                    len(display_parms) >= 3
            ) :
                display_mode = display_parms[1].lower()
                if display_mode in ("file", "tiff", "framebuffer") :
                    imgfile_name = display_parms[0]
                    seen_imgfile = imgfile_name.startswith("+") # assume I’ve seen it before
                    if seen_imgfile :
                        imgfile_name = imgfile_name[1:]
                    #end if
                    if (
                            force_auto == True and not seen_imgfile
                        or
                            force_auto == None and display_mode == "framebuffer"
                    ) :
                        imgfile_names.append(os.path.join(work_dir, imgfile_name))
                    #end if
                    if display_mode == "framebuffer" :
                        line = None
                    #end if
                #end if
            #end if
        #end do_auto_display

        def do_auto_include() :
            nonlocal line
            readarchive_match = readarchive_pat.match(line)
            if readarchive_match != None :
                parms = shlex.split(readarchive_match.group(1))
                if len(parms) != 1 :
                    syntax_error("expecting exactly one filename for ReadArchive directive")
                #end if
                line = None
                do_include(parms[0], "archives")
            #end if
        #end do_auto_include

        def submagic_autodisplay(line_rest) :
            nonlocal orig_line, replace_line
            if outfile != None and outfile_type != FILE_TYPE.RIB :
                syntax_error("%autodisplay must be in %rib file")
            #end if
            imgfile_name = new_imgfile_name()
            replace_line = \
                (
                    "Display \"%(outfile)s\" \"file\" \"rgba\""
                %
                    {"outfile" : imgfile_name}
                )
            orig_line = False
        #end submagic_autodisplay

        def submagic_display(line_rest) :
            if len(line_rest) != 1 :
                syntax_error("expecting only one arg for “display” directive")
            #end if
            collect_display(os.path.join(work_dir, line_rest[0]))
        #end submagic_display

        def submagic_include(line_rest) :
            if len(line_rest) != 1 :
                syntax_error("wrong nr args for “include” directive")
            #end if
            do_include(line_rest[0], "sources")
        #end submagic_include

        def submagic_insval(line_rest) :
            if len(line_rest) != 1 :
                syntax_error("expecting only one arg for “insval” directive")
            #end if
            expr = line_rest[0]
            try :
                val = get_ipython().ev(expr)
            except Exception as exc :
                syntax_error("insval: when trying to evaluate %s: %s" % (repr(expr), repr(exc)))
            #end try
            if isinstance(val, str) :
                cur_input.push_iter(val.split("\n"))
            elif isinstance(val, (tuple, list)) and all (isinstance(s, str) for s in val) :
                cur_input.push_iter(val)
            else :
                syntax_error("%s does not evaluate to a string or sequence of strings" % repr(expr))
            #end if
        #end submagic_insval

        def submagic_rib(line_rest) :
            if len(line_rest) != 0 :
                syntax_error("unexpected args for “rib” directive")
            #end if
            new_rib_file()
        #end submagic_rib

        def submagic_ribfile(line_rest) :
            nonlocal cur_input, outfile, line
            save_input = cur_input
            opts, args = getopt.getopt \
              (
                line_rest,
                "",
                ["autodisplay", "noautodisplay"]
              )
            if len(args) != 1 :
                syntax_error("need exactly one arg for “ribfile” directive")
            #end if
            auto_display = None
            for keyword, value in opts :
                if keyword == "--autodisplay" :
                    auto_display = True
                elif keyword == "--noautodisplay" :
                    auto_display = False
                #end if
            #end for
            rib_filename = find_file(args[0], "sources")
            new_rib_file()
            cur_input = InputStack()
            cur_input.push_file(rib_filename)
            for line in cur_input :
                do_auto_display(auto_display)
                if line != None :
                    do_auto_include()
                #end if
                if line != None :
                    outfile.write(line)
                    outfile.write("\n")
                #end if
            #end for
            outfile.close()
            outfile = None
            cur_input = save_input
            compile_rib(outfile_name)
        #end submagic_ribfile

        def submagic_sl(line_rest) :
            nonlocal outfile_name, outfile_type, outfile
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
        #end submagic_sl

        def submagic_slfile(line_rest) :
            opts, args = getopt.getopt \
              (
                line_rest,
                "",
                []
              )
            if len(args) != 1 :
                syntax_error("need exactly one arg for “slfile” directive")
            #end if
            compile_shader(find_file(args[0], "sources"))
              # aqsl puts output into current working dir by default, which is nice
        #end submagic_slfile

        def submagic_teqser(line_rest) :

            def valid_bytes(b) :
                # does b have a suitable type for an image bytes object.
                return \
                    (
                        isinstance(b, bytes)
                    or
                        isinstance(b, bytearray)
                    or
                        isinstance(b, array.array) and b.typecode == "B"
                    )
            #end valid_bytes

        #begin submagic_teqser
            valid_opts = \
                {
                    "bake" : True,
                    "compression" : True,
                    "envcube" : False,
                      # I am assuming the 6 files are input args, not values for this option
                    "envlatl" : False,
                    "filter" : True,
                    "fov(envcube)" : True,
                    "quality" : True,
                    "readval" : True,
                    "shadow" : False,
                    "swrap" : True,
                    "twrap" : True,
                    "wrap" : True,
                    "swidth" : True,
                    "twidth" : True,
                    "width" : True,
                    # todo: verbose
                }
            opts, args = getopt.getopt \
              (
                line_rest,
                "",
                list(k + ("", "=")[valid_opts[k]] for k in valid_opts)
              )
            doing_val = any("--readval" == opt[0] for opt in opts)
            doing_envcube = any("--envcube" == opt[0] for opt in opts)
            expect_args = ((2, 7)[doing_envcube], 1)[doing_val]
            if len(args) != expect_args :
                syntax_error \
                  (
                        "expecting %d args for teqser%s%s"
                    %
                        (
                            expect_args,
                            ("", " --envcube")[doing_envcube],
                            ("", " --readval")[doing_val],
                        )
                  )
            #end if
            cmd = ["teqser"]
            for keyword, value in opts :
                if keyword.startswith("--") :
                    if keyword == "--readval" :
                        try :
                            val = get_ipython().ev(value)
                        except Exception as exc :
                            syntax_error("teqser --readval: when trying to evaluate %s: %s" % (repr(value), repr(exc)))
                        #end try
                        if doing_envcube :
                            if (
                                    not isinstance(val, (tuple, list))
                                or
                                    len(val) != 6
                                or
                                    not all(valid_bytes(b) for b in val)
                            ) :
                                syntax_error("teqser --envcube --readval expects 6 bytes objects")
                            #end if
                        else :
                            if not isinstance(val, (tuple, list)) :
                                val = [val]
                            #end if
                            if len(val) != 1 or not valid_bytes(val[0]) :
                                syntax_error("teqser --readval expects 1 bytes object")
                            #end if
                        #end if
                        infiles = []
                        for b in val :
                            filename = new_texfile_name()
                            if True :
                                pngtemp = filename + ".png"
                                pngout = open(pngtemp, "wb")
                                pngout.write(b)
                                pngout.flush()
                                subprocess.run \
                                  (
                                    args = ("convert", pngtemp, filename),
                                    universal_newlines = False,
                                    check = True,
                                    timeout = timeout
                                  )
                            else :
                                # feeding PNG byte stream directly via pipe doesn’t seem to work
                                # -- convert complains with “insufficient image data”
                                subprocess.run \
                                  (
                                    args = ("convert", "png:/dev/stdin", filename),
                                    input = b,
                                    universal_newlines = False,
                                    check = True,
                                    timeout = timeout
                                  )
                            #end if
                            infiles.append(filename)
                        #end for
                        args = infiles + args
                    else :
                        keyword = keyword[2:]
                        cmd.append \
                          (
                                "-%(keyword)s%(value)s"
                            %
                                {
                                    "keyword" : keyword,
                                    "value" :
                                        (lambda : "", lambda : "=%s" % value)[valid_opts[keyword]](),
                                }
                          )
                    #end if
                #end if
            #end for
            input_files = list(find_file(f, "textures") for f in args[:-1])
            output_file = args[-1]
            teqser_output = subprocess.check_output \
              (
                args = cmd + input_files + [output_file],
                stdin = subprocess.DEVNULL,
                stderr = subprocess.STDOUT,
                universal_newlines = True,
                cwd = work_dir,
                timeout = timeout
              )
            print(teqser_output) # debug
        #end submagic_teqser

        submagics = \
            {
                "#" : lambda line_rest : None, # skip comment
                "autodisplay" : submagic_autodisplay,
                "display" : submagic_display,
                "include" : submagic_include,
                "insval" : submagic_insval,
                "rib" : submagic_rib,
                "ribfile" : submagic_ribfile,
                "sl" : submagic_sl,
                "slfile" : submagic_slfile,
                "teqser" : submagic_teqser,
            }
        in_file_submagics = {"#", "autodisplay", "include", "insval"}
          # ones which do not terminate current file contents

    #begin run_aqsis
        temp_dir = tempfile.mkdtemp(prefix = "rman-magic-")
        try :
            keep_temps = debug
            work_dir = os.path.join(temp_dir, "work")
            os.mkdir(work_dir)
              # separate subdirectory for files created by caller
            submagic_pat = re.compile(r"^\%(\w+)(?:\s+(.+))?$")
            cur_input = InputStack()
              # actually will never be more than 1 deep, since I don’t recognize
              # submagics in included files
            cur_input.push_iter(input.split("\n"))
            linenr = 0
            while True :
                line = next(cur_input, None)
                if line != None and cur_input.include_depth == 0 :
                    linenr += 1
                #end if
                orig_line = True
                if line == None or cur_input.include_depth == 0 and line.startswith("%") :
                    if line != None :
                        if line.startswith("%#") :
                            directive, line_rest = "#", []
                        else :
                            parse = submagic_pat.match(line)
                            if parse == None or len(parse.groups()) != 2 :
                                syntax_error("bad directive line")
                            #end if
                            directive, line_rest = parse.groups()
                            if line_rest != None :
                                line_rest = shlex.split(line_rest)
                            else :
                                line_rest = []
                            #end if
                        #end if
                    else :
                        directive = None
                    #end if
                    replace_line = None # initial assumption
                    if line == None or directive not in in_file_submagics :
                        if outfile != None :
                            outfile.close()
                            outfile = None
                            outfile_actions[outfile_type](outfile_name)
                        #end if
                    #end if
                    if line == None :
                        break
                    if directive not in submagics :
                        syntax_error("unrecognized submagic directive “%s”" % directive)
                    #end if
                    submagics[directive](line_rest)
                    line = replace_line # already processed
                #end if
                if orig_line and outfile_type == FILE_TYPE.RIB :
                    if line != None :
                        do_auto_display(False)
                    #end if
                    if line != None :
                        do_auto_include()
                    #end if
                #end if
                if line != None :
                    if outfile == None :
                        new_rib_file()
                    #end if
                    outfile.write(line)
                    outfile.write("\n")
                #end if
            #end while
            if len(images) == 0 :
                syntax_error("no output produced")
            #end if
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
            images
    #end run_aqsis

    # Note on args to actual magic methods:
    # “line” is whatever was typed on the %% line after the magic name.
    # “cell” is the rest of the cell contents.

    @magic.cell_magic
    def rman(self, line, cell) :
        "executes the cell contents as RenderMan, and displays returned graphical output.\n" \
        "Usage:\n" \
        "\n" \
        "    %%rman «options...»\n" \
        "\n" \
        "where valid options are\n" \
        "    --debug keeps temp files for debugging\n" \
        "    --source-search=«dir» optional directories to search for files referenced in submagics\n" \
        "    --timeout=«timeout» specifies how many seconds to wait for" \
            " subprocesses to respond (default is infinite)\n" \
        "    --verbose=«verbosity» verbosity level 0-3, default is 1\n" \
        "\n" \
        "    --archive-search=«dir» optional directory for Aqsis to find “archive” .rib files\n" \
        "    --post-process=«code» run the specified Python «code» after generating all the images." \
            " Must be used in conjunction with --return-var, and you should include" \
            " the specified variable name somewhere in «code».\n" \
        "    --procedural-search=«dir» optional directories for Aqsis to find procedural shader libraries\n" \
        "    --resource-search=«dir» optional directories to search for files referenced" \
            " in submagics and for Aqsis to find additional files\n" \
        "    --return-var=«varname» return images as a sequence of PNG byte objects in this" \
            " variable instead of displaying them\n" \
        "    --shader-search=«dir» optional directories for Aqsis to find additional compiled shader files\n" \
        "    --texture-search=«dir» optional directories for Aqsis to find texture files"
        timeout = None
        debug = False
        source_search = None
        map_aqsis_opts = \
            {
                "archive-search" : ("archives", True, True),
              # I don’t think I need “displays”
                "shader-search" : ("shaders", True, True),
                "procedural-search" : ("procedurals", True, True),
              # “resources” handled specially
                "texture-search" : ("textures", True, True),
                "progress" : ("Progress", False, False),
                "verbose" : ("verbose", True, False),
            }
        aqsis_opts = {}

        def save_search_path(search_type, new_value) :
            # sets a new value for a search-path option, including the old
            # value where there is a “&” item.
            nonlocal source_search
            if search_type == "sources" :
                old_value = source_search
            else :
                old_value = aqsis_opts.get(search_type)
            #end if
            if old_value == None :
                old_value = "&"
            #end if
            collect = []
            for item in new_value.split(":") :
                if item == "&" :
                    collect.extend(old_value.split(":"))
                else :
                    collect.append(item)
                #end if
            #end for
            new_value = ":".join(collect)
            if search_type == "sources" :
                source_search = new_value
            else :
                aqsis_opts[search_type] = new_value
            #end if
        #end save_search_path

    #begin rman
        opts, args = getopt.getopt \
          (
            shlex.split(line),
            "",
                ("debug", "post-process=", "resource-search=", "return-var=", "source-search=", "timeout=",)
            +
                tuple(k + ("", "=")[map_aqsis_opts[k][1]] for k in map_aqsis_opts)
          )
        if len(args) != 0 :
            raise getopt.GetoptError("unexpected args")
        #end if
        return_var = None
        post_process = None
        for keyword, value in opts :
            if keyword == "--debug" :
                debug = True
            elif keyword == "--resource-search" :
                for k in ("sources", "resources") :
                    save_search_path(k, value)
                #end for
            elif keyword == "--post-process" :
                post_process = value
            elif keyword == "--return-var" :
                return_var = value
            elif keyword == "--source-search" :
                save_search_path("sources", value)
            elif keyword == "--timeout" :
                timeout = float(value)
            elif keyword.startswith("--") and keyword[2:] in map_aqsis_opts :
                mapname, has_value, is_search_path = map_aqsis_opts[keyword[2:]]
                if is_search_path :
                    assert has_value
                    save_search_path(mapname, value)
                else :
                    aqsis_opts[mapname] = (None, value)[has_value]
                #end if
            #end if
        #end for
        if post_process != None and return_var == None :
            raise getopt.GetoptError("--post-process requires --return-var")
        #end if
        images = self.run_aqsis \
          (
            input = cell,
            timeout = timeout,
            debug = debug,
            source_search = source_search,
            aqsis_opts = aqsis_opts
          )
        result = None
        if return_var != None :
            get_ipython().push({return_var : images})
            if post_process != None :
                get_ipython().ex(post_process)
            #end if
        else :
            if len(images) != 0 :
                for image in images :
                    display_png(image, raw = True)
                #end for
            else :
                result = "No output!"
            #end if
        #end if
        return \
            result
    #end rman

#end RManMagic

if __name__ == "__main__" :
    get_ipython().register_magics(RManMagic)
#end if
