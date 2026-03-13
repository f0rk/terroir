import importlib
import io
import os
import re
import shutil
import sys
import tomllib
from pathlib import Path

import jinja2
import pexpect


class ModuleSourceRewriter:

    SOURCE_PATTERN = re.compile(r'(\bsource\s*=\s*")(//)([^"?]+)(\?[^"]*)?(")')

    def __init__(self, root=None):
        if root is None:
            root = self.find_git_root()

        self.root = Path(root).resolve() if root else Path.cwd()

    def find_git_root(self):
        current = Path.cwd()

        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent

        return None

    def rewrite(self, content):
        def replacer(match):
            prefix, _, path, query, suffix = match.groups()
            query = query or ""
            absolute_path = self.root / path

            return "{}{}{}{}".format(
                prefix,
                absolute_path,
                query,
                suffix,
            )

        return self.SOURCE_PATTERN.sub(replacer, content)


class App(object):

    config = None
    plugins = None
    module_rewriter = None

    def __init__(self):
        self.load_config()
        self.load_plugins()

        if self.has_git_root():
            self.module_rewriter = ModuleSourceRewriter()

    def load_config(self):

        self.config = []

        current_path = os.getcwd()

        config_files = []

        while True:

            if current_path == "/":
                break

            maybe_config_path = os.path.join(current_path, ".terroir", "config.toml")

            if os.path.exists(maybe_config_path):
                config_files.append(maybe_config_path)

            if os.path.exists(os.path.join(current_path, ".git")):
                break

            current_path, _ = os.path.split(current_path)

        config_files.reverse()

        for config_file in config_files:
            with open(config_file, "rb") as fp:
                config = tomllib.load(fp)

                self.config.append((config_file, config))

    def load_plugins(self):
        self.plugins = []

        for config_path, config in self.config:
            for plugin_name, plugin_section in config.get("plugins", {}).items():
                plugin_declaration = plugin_section["plugin"]

                config_dir = os.path.dirname(config_path)

                maybe_plugin_path = os.path.join(config_dir, plugin_declaration)

                if plugin_declaration == "terroir_plugin.py" and os.path.exists(maybe_plugin_path):
                    try:
                        sys.path.insert(0, config_dir)
                        module = importlib.import_module("terroir_plugin")
                        importlib.reload(module)
                    finally:
                        sys.path.remove(config_dir)

                    self.plugins.append(module.Plugin())
                else:
                    module_name, plugin_object_name = plugin_declaration.split("::")

                    module = importlib.import_module(module_name)

                    plugin_class = getattr(module, plugin_object_name)

                    self.plugins.append(plugin_class())

    def has_git_root(self):
        current = Path.cwd()

        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent

        return None

    def render(self, tf_file, template_variables):

        for plugin in self.plugins:
            if hasattr(plugin, "update_template_variables"):
                plugin.update_template_variables(
                    template_variables,
                    tf_file=tf_file,
                )

        with open(tf_file, "rt") as tf_fp:
            content = tf_fp.read()

            if self.module_rewriter:
                content = self.module_rewriter.rewrite(content)

            env = jinja2.Environment(
                loader=jinja2.BaseLoader,
                undefined=jinja2.StrictUndefined,
            )
            template = env.from_string(content)

        try:
            rendered = template.render(
                **template_variables,
            )

            for plugin in self.plugins:
                if hasattr(plugin, "post_render_callback"):
                    plugin.post_render_callback(
                        rendered,
                        tf_file=tf_file,
                    )

            return rendered
        except jinja2.exceptions.UndefinedError:
            sys.stderr.write(
                "(hint: did you forget define a variable?)\n"
            )
            sys.stderr.flush()
            raise

    def run(self, template_variables=None):
        if template_variables is None:
            template_variables = {}

        exitstatus = 0

        tf_files = []
        tfbak_files = []
        for name in os.listdir():
            if name.endswith(".tf"):
                tf_files.append(name)
            if name.endswith(".tfbak"):
                tfbak_files.append(name)

        if tfbak_files:
            if sys.argv[1] == "restore":
                self.restore_tfbak_files(tfbak_files)
            else:
                sys.stderr.write(
                    "terroir detected .tfbak files, which indicates a problem "
                    "cleaning up from a previous terroir run. use `terroir "
                    "restore` to overwrite the existing files with the .tfbak "
                    "ones, or manually remove them if you have made changes to "
                    "the original files.\n"
                )
                sys.stderr.flush()
                return 1

        try:
            for tf_file in tf_files:

                tfbak_file = tf_file + "bak"
                shutil.copyfile(tf_file, tfbak_file)

                rendered = self.render(tf_file, template_variables)
                with open(tf_file, "wt") as tf_fp:
                    tf_fp.write(rendered)

            if sys.argv[1] == "--":
                exitstatus, _ = self.run_command(sys.argv[2:])
            else:
                exitstatus, _ = self.run_terraform(sys.argv[1:])

        finally:
            for tf_file in tf_files:
                tfbak_file = tf_file + "bak"
                if os.path.exists(tfbak_file):
                    shutil.copyfile(tfbak_file, tf_file)
                    os.unlink(tfbak_file)
            if sys.argv[1] == "apply":
                if os.path.exists(".terraform") and os.path.isdir(".terraform"):
                    for dirpath, dirnames, filenames in os.walk(".terraform"):
                        dirnames[:] = [d for d in dirnames if d != "providers"]
                        for filename in filenames:
                            os.unlink(os.path.join(dirpath, filename))

        return exitstatus

    def restore_tfbak_files(self, tfbak_files):
        for tfbak_file in tfbak_files:

            tf_file = re.sub(r'[.]tfbak$', ".tf", tfbak_file)

            shutil.copyfile(tfbak_file, tf_file)
            os.unlink(tfbak_file)

    def run_terraform(self, args, retries_remaining=2, echo_output=True):

        class Capture(object):

            def __init__(self):
                self.buffer = io.StringIO()

            def write(self, s):
                sys.stdout.write(s)
                self.buffer.write(s)

            def flush(self):
                sys.stdout.flush()

        process = pexpect.spawn(
            "terraform",
            args=args,
            encoding="utf-8",
            timeout=None
        )

        capture = Capture()

        def cleanup():
            process.read()
            process.wait()
            process.close()

        process.logfile_read = capture
        process.logfile_send = None
        process.setecho(False)

        expected_text = [
            "initialization required",
            "Module not installed",
            "Missing required provider",
            "Enter a value:",
            pexpect.EOF,
        ]

        found_index = process.expect(expected_text)

        # initialization required, run to completion, re-call with init
        if found_index in (0, 1, 2):

            cleanup()

            if retries_remaining > 0:
                self.run_terraform(
                    ["init"],
                    retries_remaining=(retries_remaining - 1),
                )

                return self.run_terraform(
                    args,
                    retries_remaining=(retries_remaining - 1),
                )

            raise Exception(
                "terraform failed to execute: {}"
                .format(capture.buffer.getvalue())
            )

        # user needs to type
        elif found_index == 3:
            answer = input("")
            process.sendline(answer)

        # program ran to completion, no input needed
        elif found_index == 4:
            pass

        else:
            raise Exception(
                "Implementation Error: unexpected found_index {}"
                .format(found_index)
            )

        # cleanup
        cleanup()

        return process.exitstatus, capture.buffer.getvalue()

    def run_command(self, args):

        exec_path = args[0]
        if "/" not in exec_path:
            maybe_exec_path = shutil.which(exec_path)
            if maybe_exec_path:
                exec_path = maybe_exec_path

        exitstatus = os.spawnvp(os.P_WAIT, exec_path, args)

        return exitstatus, None
