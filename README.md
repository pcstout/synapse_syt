# Synapse Folder Check In/Out Tracking

A utility to track [Synapse](https://www.synapse.org/) Folder check ins/outs.

## Usage

```
usage: syt.py [-h] [-f] [-u USERNAME] [-p PASSWORD]
              {checkout,checkin,show} entity-id

positional arguments:
  {checkout,checkin,show}
                        The command to execute.
  entity-id             The ID of the Synapse Folder to execute the command
                        on. Can be a Project ID for the show command.

optional arguments:
  -h, --help            show this help message and exit
  -f, --force           Force a check-in.
  -u USERNAME, --username USERNAME
                        Synapse username.
  -p PASSWORD, --password PASSWORD
                        Synapse password.

```