# Copyright 2018-present, Bill & Melinda Gates Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import argparse
import getpass
import calendar
import datetime
import numpy
import synapseclient
from synapseclient import Project, Folder, File, Column, EntityViewSchema
import synapseutils

try: 
    import queue
except ImportError:
        import Queue as queue


class Syt:

    SYT_VIEW_NAME = 'syt'

    ANNO_CHECKED_OUT_BY_ID = '_syt_by_id'
    ANNO_CHECKED_OUT_BY_NAME = '_syt_by_name'
    ANNO_CHECKED_OUT_DATE = '_syt_date'
    ALL_ANNO = [ANNO_CHECKED_OUT_BY_ID,
                ANNO_CHECKED_OUT_BY_NAME, ANNO_CHECKED_OUT_DATE]

    ADMIN_PERMS = ['UPDATE', 'DELETE', 'CHANGE_PERMISSIONS',
                   'CHANGE_SETTINGS', 'CREATE', 'DOWNLOAD', 'READ', 'MODERATE']

    def __init__(self, entity_id, verbose=False, username=None, password=None):
        self.verbose = verbose
        self._synapse_client = None
        self._username = username
        self._password = password
        self._user = None
        self._entity_id = entity_id
        self._entity = None
        self._project = None
        self._syt_view = None

        # Disable the synapseclient progress output.
        if not verbose:
            synapseclient.utils.printTransferProgress = lambda *a, **k: None

    def _load(self):
        self.synapse_login()
        self._user = self._synapse_client.getUserProfile()
        self._load_entity()
        self._ensure_syt_view()
        return self._entity != None

    def show(self):
        """
        Show all entities that are checked out.
        """
        print('Show Checked out entities...')
        if (not self._load()):
            return

        checked_out = []

        print('Loading Check-outs...')
        walker = None

        if isinstance(self._entity, Project):
            walker = self._walk_all_checked_out()
        else:
            walker = self._walk_checked_out_children(self._entity)
            if self._is_checked_out(self._entity):
                checked_out.append(self._entity)

        for entity in walker:
            checked_out.append(entity)

        if len(checked_out):
            for entity in checked_out:
                print('-' * 80)
                print('{0}: {1} ({2})'.format(
                    entity.entityType.split('.')[-1].replace('Entity', ''), entity.name, entity.id))
                print('Checked out by: {0} ({1})'.format(
                    entity[self.ANNO_CHECKED_OUT_BY_NAME][0], entity[self.ANNO_CHECKED_OUT_BY_ID][0]))
                print('Checked out on: {0}'.format(
                    entity[self.ANNO_CHECKED_OUT_DATE][0]))
        else:
            print('No checked out entities found.')

    def checkout(self, checkout_path=os.getcwd(), sync=False, force=False):
        """
        Checks out an Entity.
        """
        print('Checking out...')
        if (not self._load()):
            return

        if force and not self._is_admin_on_project():
            print('Must have administrator privileges to force check-out.')
            return

        if (self._is_checked_out(self._entity)):
            if (force):
                print('WARNING: Entity already checked out by {0}'.format(
                    self._entity[self.ANNO_CHECKED_OUT_BY_NAME][0]))
            else:
                print('Entity already checked out by {0}. Aborting.'.format(
                    self._entity[self.ANNO_CHECKED_OUT_BY_NAME][0]))
                return

        if not isinstance(self._entity, Project):
            print('Checking Parent Check-outs...')
            for parent in self._walk_parents(self._entity, [Project, Folder]):
                if (self._is_checked_out(parent)):
                    parent_id = parent.id
                    parent_name = parent.name
                    parent_by_name = parent[self.ANNO_CHECKED_OUT_BY_NAME][0]

                    if (force):
                        print('WARNING: Parent: {0} ({1}) is checked out by {2}.'.format(
                            parent_name, parent_id, parent_by_name))
                    else:
                        print('Parent: {0} ({1}) is checked out by {2}. Aborting.'.format(
                            parent_name, parent_id, parent_by_name))
                        return

        print('Checking Child Check-outs...')
        checked_out_child = next(
            self._walk_checked_out_children(self._entity), None)
        if (checked_out_child):
            child_id = checked_out_child.id
            child_name = checked_out_child.name
            child_by_name = checked_out_child[self.ANNO_CHECKED_OUT_BY_NAME][0]

            if (force):
                print('WARNING: Child: {0} ({1}) is checked out by {2}.'.format(
                    child_name, child_id, child_by_name))
            else:
                print('Child: {0} ({1}) is checked out by {2}. Aborting.'.format(
                    child_name, child_id, child_by_name))
                return

        if (sync):
            print('Syncing Folders and Files...')
            # Download all the folders and files.
            entities = synapseutils.syncFromSynapse(
                self._synapse_client, self._entity, path=checkout_path)

            print('Checked out files:')
            for f in entities:
                print('  - {0}'.format(f.path))

            # Write the Synapse ID of the checked out object so we can easily get it for check-in.
            Syt.write_dot_syt(checkout_path, self._entity.id)

        self._entity[self.ANNO_CHECKED_OUT_BY_ID] = self._user.ownerId
        self._entity[self.ANNO_CHECKED_OUT_BY_NAME] = self._user.userName
        self._entity[self.ANNO_CHECKED_OUT_DATE] = datetime.datetime.now()
        self._synapse_client.store(self._entity)

        print('Check-out was successful')

    def checkin(self, checkout_path=os.getcwd(), sync=False, force=False):
        """
        Checks in an Entity.
        """
        print('Checking in...')
        if (not self._load()):
            return

        if force and not self._is_admin_on_project():
            print('Must have administrator privileges to force check-in.')
            return

        if (not self._is_checked_out(self._entity)):
            if (force):
                print('WARNING: Entity not checked out.')
            else:
                print('Entity not checked out. Aborting.')
                return

        checked_out_by_id = self._entity[self.ANNO_CHECKED_OUT_BY_ID][0]

        if (not force and checked_out_by_id != self._user.ownerId):
            if (force):
                print('WARNING: Entity is currently checked out by {0}.'.format(
                    self._entity[self.ANNO_CHECKED_OUT_BY_NAME][0]))
            else:
                print(
                    'Entity can only be checked in by {0}. Aborting.'.format(self._entity[self.ANNO_CHECKED_OUT_BY_NAME][0]))
                return

        # Upload the files
        if (sync):
            print('Syncing Folders and Files...')
            manifest_filename = os.path.join(
                checkout_path, 'SYNAPSE_METADATA_MANIFEST.tsv')
            if (os.path.exists(manifest_filename)):
                synapseutils.syncToSynapse(
                    self._synapse_client, manifest_filename, sendMessages=False)
            else:
                print(
                    'Manifest file not found in: "{0}". Folder/Files will not be uploaded to Synapse.'.format(checkout_path))

        for key in self.ALL_ANNO:
            if key in self._entity.annotations:
                del self._entity.annotations[key]

        self._synapse_client.store(self._entity)

        print('Check-in was successful')

    def _is_checked_out(self, entity):
        return self.ANNO_CHECKED_OUT_BY_ID in entity

    def _ensure_syt_view(self):
        """
        Ensure the syt table/view exists for the project.
        """
        try:
            # This will fail if the schema doesn't exist. This is a synapseclient bug.
            self._syt_view = self._synapse_client.get(EntityViewSchema(
                name=self.SYT_VIEW_NAME, parent=self._project), downloadFile=False)
        except:
            pass

        if self._syt_view == None:
            evs = EntityViewSchema(name=self.SYT_VIEW_NAME, parent=self._project,
                                   scopes=[self._project], properties={'viewTypeMask': 9})

            # Delete the 'type' property so we can set our own viewTypeMask to Files and Folders.
            evs.pop('type')

            # Since we removed 'type' we have to manually populate the base columns.
            evs.addColumn(Column(name='id', columnType='ENTITYID'))
            evs.addColumn(Column(name='parentId', columnType='ENTITYID'))
            evs.addColumn(Column(name='projectId', columnType='ENTITYID'))
            evs.addColumn(Column(name='type', columnType='STRING'))
            evs.addColumn(
                Column(name='name', columnType='STRING', maximumSize=256))

            evs.addColumn(
                Column(name=self.ANNO_CHECKED_OUT_BY_ID, columnType='STRING'))
            evs.addColumn(
                Column(name=self.ANNO_CHECKED_OUT_BY_NAME, columnType='STRING'))
            evs.addColumn(
                Column(name=self.ANNO_CHECKED_OUT_DATE, columnType='DATE'))

            self._syt_view = self._synapse_client.store(evs)

    def _walk_all_checked_out(self):
        """
        Gets the Project and all files and folders that are checked out for the whole project.
        """
        tquery = self._synapse_client.tableQuery(
            "select id, name, type, {0}, {1}, {2} from {3} where {0} <> '' ".format(
                self.ANNO_CHECKED_OUT_BY_ID,
                self.ANNO_CHECKED_OUT_BY_NAME,
                self.ANNO_CHECKED_OUT_DATE,
                self._syt_view.id
            ),
            resultsAs='rowset'
        )

        # Add the project if it's checked out since Projects are not in the view.
        if self._is_checked_out(self._project):
            yield self._project

        for row in tquery.rowset.rows:
            yield self._synapse_client.get(row.values[0], downloadFile=False)

    def _walk_parents(self, entity, parent_types=[Project]):
        """
        Yields all the parent entities of a specific type.
        """
        q = queue.Queue()
        q.put(entity.parentId)

        while not q.empty():
            parent = self._synapse_client.get(q.get(), downloadFile=False)

            for parent_type in parent_types:
                if (isinstance(parent, parent_type)):
                    yield parent

            # Stop when we hit the Project.
            # Parents exist beyond the project but users don't have access to them.
            if not isinstance(parent, Project):
                q.put(parent.parentId)

    def _walk_checked_out_children(self, parent):
        """
        Walks all the children entities and yields any that are checked out.
        """
        q = queue.Queue()
        q.put(parent.id)

        while not q.empty():
            parent_id = q.get()

            tquery = self._synapse_client.tableQuery(
                "select id, type, {0} from {1} where parentId = '{2}' ".format(
                    self.ANNO_CHECKED_OUT_BY_ID,
                    self._syt_view.id,
                    parent_id
                ),
                resultsAs='rowset'
            )

            for row in tquery.rowset.rows:
                id = row.values[0]
                type = row.values[1]
                by_id = row.values[2]

                if by_id:
                    yield self._synapse_client.get(id, downloadFile=False)

                if type == 'folder':
                    q.put(id)

    def _load_entity(self):
        """
        Loads the Entity and its Project.
        """
        print('Loading Entity...')
        self._entity = self._synapse_client.get(
            self._entity_id, downloadFile=False)

        type = self._entity.entityType.split('.')[-1].replace('Entity', '')

        if type in ['Project', 'Folder', 'File']:
            if (type != 'Project'):
                print('Loading Project...')
                self._project = self._walk_parents(
                    self._entity, [Project]).next()
                print('{0} "{1}" ({2}) from Project "{3}" ({4})'.format(
                    type, self._entity.name, self._entity.id, self._project.name, self._project.id))
            else:
                self._project = self._entity
        else:
            print('Found {0} {1} ({2})'.format(
                type, self._entity.name, self._entity.id))
            print('Only Projects, Folders, and Files can be checked in/out. Aborting.')
            self._entity = None
            self._project = None

        return self._project != None

    def _is_admin_on_project(self):
        """
        Gets if the user has admin privileges on the project.
        """
        user_perms = self._synapse_client.getPermissions(
            self._project, self._user.ownerId)

        admin_perms = set(self.ADMIN_PERMS)

        if (set(user_perms) == admin_perms):
            return True
        else:
            # Check the groups.
            acl = self._synapse_client._getACL(self._project)

            for resourceAccess in acl['resourceAccess']:
                principalId = resourceAccess['principalId']
                try:
                    team = self._synapse_client.getTeam(principalId)
                    team_members = self._synapse_client.getTeamMembers(team)
                    for team_member in team_members:
                        if team_member['member']['ownerId'] == self._user.ownerId:
                            if set(resourceAccess['accessType']) == admin_perms:
                                return True
                except synapseclient.exceptions.SynapseHTTPError as ex:
                    # This will 404 when fetching a User instead of a Team.
                    if ex.response.status_code != 404:
                        raise ex

    def synapse_login(self):
        """
        Logs into Synapse.
        """
        print('Logging into Synapse...')
        syn_user = self._username or os.getenv('SYNAPSE_USER')
        syn_pass = self._password or os.getenv('SYNAPSE_PASSWORD')

        if syn_user == None:
            syn_user = input('Synapse username: ')

        if syn_pass == None:
            syn_pass = getpass.getpass(prompt='Synapse password: ')

        self._synapse_client = synapseclient.Synapse()
        self._synapse_client.table_query_timeout = 600
        self._synapse_client.login(syn_user, syn_pass, silent=True)

    @staticmethod
    def get_dot_syt_filename(path):
        """
        Gets the full filename of the .syt file.
        """
        return os.path.join(path, '.syt')

    @staticmethod
    def write_dot_syt(path, entity_id):
        """
        Writes to the .syt file.
        """
        with open(Syt.get_dot_syt_filename(path), "w") as syt_file:
            syt_file.write(entity_id)

    @staticmethod
    def read_dot_syt(path):
        """
        Reads the .syt file.
        """
        if (not os.path.exists(Syt.get_dot_syt_filename(path))):
            return None

        with open(Syt.get_dot_syt_filename(path), "r") as syt_file:
            return syt_file.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=[
                        'checkout', 'checkin', 'show'], help='The command to execute.')
    parser.add_argument('entity_id', metavar='entity-id', nargs='?',
                        help='The ID of the Synapse Entity to execute the command on.')
    parser.add_argument('checkout_path', metavar='checkout-path',
                        nargs='?', default=os.getcwd(), help='The local path to sync with Synapse.')
    parser.add_argument('-s', '--sync', help='Download or upload when checking in/out.',
                        default=False, action='store_true')
    parser.add_argument('-f', '--force', help='Force a check in/out.',
                        default=False, action='store_true')
    parser.add_argument('-v', '--verbose', help='Turn on verbose output.',
                        default=False, action='store_true')
    parser.add_argument('-u', '--username',
                        help='Synapse username.', default=None)
    parser.add_argument('-p', '--password',
                        help='Synapse password.', default=None)
    args = parser.parse_args()

    entity_id = args.entity_id
    checkout_path = args.checkout_path

    # Load the entity_id from .syt if not specified.
    if (not entity_id):
        checkout_path = os.getcwd()
        entity_id = Syt.read_dot_syt(checkout_path)
        if (not entity_id):
            print('Entity ID not specified, .syt file not found in: {0}'.format(
                Syt.get_dot_syt_filename(checkout_path)))
            return
    elif (not entity_id.lower().startswith('syn')):
        checkout_path = entity_id
        entity_id = Syt.read_dot_syt(entity_id)
        if (not entity_id):
            print(
                'Entity ID not specified, .syt file not found in checkout-path: {0}'.format(checkout_path))
            return

    syt = Syt(entity_id, verbose=args.verbose,
              username=args.username, password=args.password)

    if args.command == 'checkin':
        syt.checkin(checkout_path, args.sync, args.force)
    elif args.command == 'checkout':
        syt.checkout(checkout_path, args.sync, args.force)
    else:
        syt.show()


if __name__ == "__main__":
    main()
