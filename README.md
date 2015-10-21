# arazu

A simple tool for helping deploy projects using git

### tl;dr

Arazu is a script to take code from repo A, call its build command, and commit
the result into repo B. It was created to make deploying static sites trivial
by pushing the build output into a branch that gets automatically deployed.



### More Info

Provides single-command management of the build/deploy cycle for projects that
generate an output folder of some kind (originally for static sites but can be
for anything that fits the model).

Arazu is not a build system - you should already have a system that builds your
finished output. Instead, arazu is simply a helper tool that runs your build
command, commits the output into a separate repository and/or branch, and
pushes to it with a helpful commit message. The only goal is to remove the
manual step of deploying, particularly for things where the deployable product
lives in a repository but the source should not be included with it (like
static sites).

Assumes the code lives in git and the project can be deployed via git push.
Supports things like hosting the code in one repository (maybe local, private,
or on-prem) and deploying it using a different one (github pages, heroku, ci,
etc).


### Quick Start:

clone this repo somewhere then install locally via pip

```pip -e path/to/arazu```

create a starting template

```arazu init```

fill out the template with your project info

```arazu deploy```


### Full Lifecycle:
  your project already works and builds to a single output folder

  `arazu deploy`

    - arazu bails if you have local changes - stash them to continue
    - arazu runs your configured build command
    - arazu creates a new deploy folder (defaults to .deploy)
    - arazu clones your deploy repository to the deploy folder and checks
    out your deploy branch
    - arazu copies your configured build output folder to the deploy folder
    - arazu adds everything (using `git add .`) and commits it with a simple
    commit message included the current date/time and the commit hash from
    the source repository.
