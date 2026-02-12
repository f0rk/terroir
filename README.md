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

Custom Functions:
-----------------

You can provide a path to `terroir` that contains custom functions that will be
made available to your templates by setting the `TERROIR_CUSTOM_FUNCTIONS_DIR`
environment variable. This path can contain Python to be loaded, and they must
end in `.py` to be loaded.

Each file must contain a function called `main`. The name of the function in
your templates will be the name of the file minus the extension. For example, a
file named `example.py` will be available in your templates as `example`. You
can optionally define a `name` attribute in the file, in which case that will
be used instead of the filename.

Given the following file in `~/custom_functions/my_function.py`:
```python
import os

# uncomment this line to assign the function to the name `different_name`
# name = "different_name"

def main():
    return f"Hello, {os.getlogin()}"
```

you could use it in your templates like this:
```jinja2
{{ my_function() }}
```

and making terroir aware of your custom functcion directory:
```
$ TERROIR_CUSTOM_FUNCTIONS_DIR="${HOME}/custom_functions" terroir plan
```
