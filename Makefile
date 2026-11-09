# Guardian Heroes recomp: a game repository for the satrecomp toolkit (satrecomp/README.md).
# The toolkit copy in satrecomp/ is made by satrecomp/tools/sync-toolkit.sh; never change it here.
GAME ?= guardianheroes
SR ?= satrecomp
# Your own disc image. It is never part of the repository (see .gitignore).
DISC ?= Guardian Heroes (USA)/Guardian Heroes (USA).cue
include $(SR)/build.mk
