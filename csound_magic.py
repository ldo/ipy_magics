#+
# Cell magic for IPython that allows the inclusion of Csound code
# <http://www.csounds.com/>. The audio will be played by the notebook
# server.
#
# Copyright 2016, 2019 Lawrence D'Oliveiro <ldo@geek-central.gen.nz>.
# Licensed under CC-BY-SA <http://creativecommons.org/licenses/by-sa/4.0/>.
#-

import os
import subprocess
import tempfile
import gzip
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

        def syntax_error(reason) :
            raise SyntaxError(reason, ("<cell input>", linenr, None, line))
        #end syntax_error

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
                self.push_iter \
                  (
                    (open, gzip.open)[filename.endswith(".gz")](filename, "rt")
                        .read().split("\n")
                  )
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

        def do_include(filename) :
            cur_input.push_file(filename)
        #end do_include

        def submagic_include(line_rest) :
            if len(line_rest) != 1 :
                syntax_error("wrong nr args for “include” directive")
            #end if
            do_include(line_rest[0])
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

        submagics = \
            {
                "#" : lambda line_rest : None, # skip comment
                "include" : submagic_include,
                "insval" : submagic_insval,
            }

    #begin csound
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
            if keep_temps :
                print("keeping temp files in %s" % temp_dir)
            #end if
            cs_file_name = os.path.join(temp_dir, "in.csd")
            sound_file_name = os.path.join(temp_dir, "out.wav")
            submagic_pat = re.compile(r"^\%(\w+)(?:\s+(.+))?$")
            cur_input = InputStack()
              # actually will never be more than 1 deep, since I don’t recognize
              # submagics in included files
            cur_input.push_iter(cell.split("\n"))
            cs_file = open(cs_file_name, "wt")
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
                    if line == None :
                        break
                    if directive not in submagics :
                        syntax_error("unrecognized submagic directive “%s”" % directive)
                    #end if
                    submagics[directive](line_rest)
                    line = None # already processed
                #end if
                if line != None :
                    cs_file.write(line)
                    cs_file.write("\n")
                #end if
            #end while
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
