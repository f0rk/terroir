import io
import os
import re
import shutil
import sys

import jinja2
import pexpect


class App(object):

    def render(self, tf_file, template_variables):

        with open(tf_file, "rt") as tf_fp:
            env = jinja2.Environment(
                loader=jinja2.BaseLoader,
                undefined=jinja2.StrictUndefined,
            )
            template = env.from_string(tf_fp.read())

        try:
            rendered = template.render(
                **template_variables,
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

            exitstatus, _ = self.run_terraform(sys.argv[1:])

        finally:
            for tf_file in tf_files:
                tfbak_file = tf_file + "bak"
                if os.path.exists(tfbak_file):
                    shutil.copyfile(tfbak_file, tf_file)
                    os.unlink(tfbak_file)
            if sys.argv[1] == "apply":
                if os.path.exists(".terraform.lock.hcl"):
                    os.unlink(".terraform.lock.hcl")
                if os.path.exists(".terraform") and os.path.isdir(".terraform"):
                    shutil.rmtree(".terraform")

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
            "Enter a value:",
            pexpect.EOF,
        ]

        found_index = process.expect(expected_text)

        # initialization required, run to completion, re-call with init
        if found_index == 0:

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
        elif found_index == 1:
            answer = input("")
            process.sendline(answer)

        # program ran to completion, no input needed
        elif found_index == 2:
            pass

        else:
            raise Exception(
                "Implementation Error: unexpected found_index {}"
                .format(found_index)
            )

        # cleanup
        cleanup()

        return process.exitstatus, capture.buffer.getvalue()
