terroir
=======

goût de terroir - the taste of the place
----------------------------------------

`terroir` is a wrapper around `terraform`, providing users with the ability to
treat .tf files as templates (in particular, jinja2 templates). It accepts
(simply passes through) all commands, but before running terraform, it
processes the files as jinja2 templates. The only injected template value
(currently) is python's `os` module, which will give you access to environment
variables. Future releases will give the user more control over what sources of
information are added.

The primary motivation behind this tool is to allow terraform's backend
configuration to be "dynamic", i.e. to allow setting information such as the
state bucket, state key, etc. based on some other information. When these
values change, terraform will also require `terraform init` to be run, which is
handled automatically by terroir.

Usage:
------

```!sh
$ TERRAFORM_STATE_BUCKET=your-state-bucket terroir plan
Acquiring state lock. This may take a few moments...
Refreshing Terraform state in-memory prior to plan...
The refreshed state will be used to calculate this plan, but will not be
persisted to local or remote state storage.

data.terraform_remote_state.vpc: Refreshing state...
aws_s3_bucket.files: Refreshing state...

------------------------------------------------------------------------

No changes. Infrastructure is up-to-date.

This means that Terraform did not detect any differences between your
configuration and real physical resources that exist. As a result, no
actions need to be performed.
Releasing state lock. This may take a few moments...
```

Just like a regular plan run.

Apply is supported as well, including interactive yes/no:
```!sh
$ TERRAFORM_STATE_BUCKET=your-state-bucket terroir apply
data.terraform_remote_state.vpc: Refreshing state...
aws_s3_bucket.files: Refreshing state...
An execution plan has been generated and is shown below.
Resource actions are indicated with the following symbols:
  ~ update in-place

Terraform will perform the following actions:
...
Plan: 0 to add, 1 to change, 0 to destroy.

Do you want to perform these actions?
  Terraform will perform the actions described above.
  Only 'yes' will be accepted to approve.

  Enter a value: yes

aws_s3_bucket.files: Modifying...
aws_s3_bucket.files: Still modifying...
Apply complete! Resources: 0 added, 1 changed, 0 destroyed.

Outputs:

files_bucket = the-filez-bucket
```

Here is what a templated file might look like:
```!tf
terraform {
  backend "s3" {
    bucket         = "{{ os.environ["TERRAFORM_STATE_BUCKET"] -}}"
    key            = "state.tfstate"
    region         = "us-east-1"
    dynamodb_table = "pop-and-lock"
  }
}
```

Configuration:
--------------

`terroir` also has a configuration file, which should generally be placed in
the root of the repo at `.terroir/config.toml`. This configuration file allows
you set environment variables that will be loaded automatically when `terroir`
is run with either `terroir --env=staging`  or `TERROIR_ENV=staging terroir`
(if the named env is staging).

```!toml
[env]
DEFAULT_REGION = "us-east-1"

[env.staging]
AWS_ACCOUNT_ID = "000000000000000"

[env.prod]
AWS_ACCOUNT_ID = "111111111111111"
```

This example config will always apply `DEFAULT_REGION` to the environ, and when
the env is staging, will supply `AWS_ACCOUNT_ID` with the value
`000000000000000`.

`terroir` also supports plugins. The plugin system allows you to import python
code, which can then be invoked to update/apply template variables before
render, or to take actions on a terraform file post rendering. In this way you
can make further programmatic updates, if necessary. An example config is:

```!toml
[[plugins]]
plugin = "terroir_plugin.py"
```

This will load a file at `.terroir/terroir_plugin.py` as a plugin, an example
of which is as follows:

```!python
import datetime
import os
import re


class Plugin:
    def update_template_variables(self, template_variables, tf_file=None):
        template_variables["get_current_time"] = lambda: datetime.datetime.now()

    def post_render_callback(self, rendered, tf_file=None):
        if os.environ["TERROIR_ENV"] == "staging" and re.search("prod", rendered):
            raise ValueError("unexpected prod reference in staging env render!")
```

Plugins can also be written as an arbitrary import of available python code, for example:

```!toml
[[plugins]]
plugin = "myterroir.plugins.env::EnvPlugin"
```

This will perform the equivalent of:

```!python
from myterroir.plugins.env import EnvPlugin
plugin = EnvPlugin()
```

Such a plugin might be written as:

```!python
import sys


class EnvPlugin:
    def update_template_variables(self, template_variables, tf_file=None):
        template_variables["sys"] = sys
```

If the call to `update_template_variables` returns a value, the `template_variables` will be replaced with that value. For example:

```!python
class Plugin:
    def update_template_variables(self, template_variables, tf_file=None):
        return {}
```

Will result in `template_variables` being set to an empty dictionary.

If the call to `post_render_callback` returns a value, the `rendered` text will be replace with that value. For example:

```!python
import re


class Plugin:
    def post_render_callback(self, rendered, tf_file=None):
        return re.sub("production-", "prod-", rendered)
```

Will result in all instances of `production-` being replaced with `prod-` in the output.
