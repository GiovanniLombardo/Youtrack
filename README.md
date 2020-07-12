## Youtrack-Exchange

### Aim of the project
The project main aim is to generate tooling for custom selective backup and restore of issues 
hosted on JetBrains(r) YouTrack servers. With those tooling users are empowered to transfer the 
knowledge encoded into the content of the issues between different systems on different work 
domains. My use case for example is to share the knowledge acquired on some personal projects 
stored on the JetBrains(r) YouTrack server instance running on my laptop with the JetBrains(r) 
YouTrack server running on the computer I use at work and vice versa. 

The JetBrains(r) YouTrack Web UI already exposes a backup feature able to save issues and 
projects but, in my humble opinion, with huge lack of granularity. It can either make a backup 
or not make it. It cannot, as far as I know, backing up only a subset of the available issues 
and restore their content on a different JetBrains(r) YouTrack server instance keeping account
of differences, duplication, etc.. Basically the restore of a backup overwrites the the current 
data. Moreover, the backup produced by a JetBrains(r) YouTrack server instance version may 
require further conversion steps in order to be used with newer JetBrains(r) YouTrack server 
instances. 

### Components
At the time of this writing the idea is to have two command line executables: one for backing
up selectively issues of projects of a given JetBrains(r) YouTrack server instance and another 
one to perform "content wise" restoration of issues on a different JetBrains(r) YouTrack server 
instance. 

##### Backup: how does it work?
The backup executable expects getting from command line the `URL` of the YouTrack instance, the 
access token of the YouTrack instance and the output folder where the issues and their data will
be stored. The default `backup all` behaviour can be customized by selecting issues and projects 
to be backed up by specifying the corresponding command line option and relative arguments. 

The backup utility will then download all the selected issues of the selected projects, along
with their metadata (actually unused), attachments, `[todo]` comments and comments attachments; 
`[todo]` in a sequential fashion, and will put them in a compressed not `[todo]` encrypted 
archive in the given `output` folder. 

##### Backup: usage
Here is what the output of the backup utility looks like when invoked with the `--help` or `-h` 
option at the command line. 

```shell script
user@host$ ./backup.py --help
(c) 2020 Giovanni Lombardo mailto://g.lombardo@protonmail.com
backup.py version 1.0.0

usage: backup.py [-h] [-v] [-p PRJS [PRJS ...]] [-i IID [IID ...]]
                 url token output

It allows custom selective youtrack project's issue backup.

positional arguments:
  url                   The URL of the YouTrack instance.
  token                 The to use with the given instance.
  output                The destination folder.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         It shows more verbose output.
  -p PRJS [PRJS ...], --projects PRJS [PRJS ...]
                        When given only the issue of the given projects are
                        considered.
  -i IID [IID ...], --issue-ids IID [IID ...]
                        When given only the issues with the given id are
                        considered.
```

##### Restore: how does it work?

##### Restore: usage

### Behavioural choices

+ The software has been designed assuming that **project's names will not ends with `-\d+\.zip`**. 
Please before using the software against your JetBrains(r) YouTrack server instance ensure that the
name of the projects follow the above constraint, otherwise it will not work correctly in such cases. 