#!/usr/bin/env python

# Copyright 2017-present, Bill & Melinda Gates Foundation
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
from synapseclient import Project, Folder, File, Team, TeamMember
from synapseclient import Team, TeamMember
from synapseclient import Schema, Column, Table, Row, RowSet
import synapseutils


class Syt:

    ANNO_CHECKED_OUT_BY_ID = '_syt_by_id'
    ANNO_CHECKED_OUT_BY_NAME = '_syt_by_name'
    ANNO_CHECKED_OUT_DATE = '_syt_date'
    ANNO_CHECKED_OUT_ETAG = '_syt_etag'
    ALL_ANNO = [ANNO_CHECKED_OUT_BY_ID, ANNO_CHECKED_OUT_BY_NAME,
                ANNO_CHECKED_OUT_DATE, ANNO_CHECKED_OUT_ETAG]

    def __init__(self, entity_id, username=None, password=None):
        self._synapse_client = None
        self._username = username
        self._password = password
        self._user = None
        self._entity_id = entity_id
        self._entity = None
        self._project = None

    def _load(self):
        self.synapse_login()
        self._user = self._synapse_client.getUserProfile()
        self._load_entity()
        return self._entity != None

    def show(self):
        print('Show Checked out entities...')
        if (not self._load()):
            return

        entities = [self._entity]

        entities += self._get_children(self._entity)

        checked_out = []

        for entity in entities:
            if (self._is_checked_out(entity)):
                checked_out.append(entity)

        if (len(checked_out)):
            for entity in checked_out:
                print('-' * 80)
                print('Entity: {0} ({1})'.format(entity.name, entity.id))
                print('Checked out by: {0} ({1})'.format(
                    entity[self.ANNO_CHECKED_OUT_BY_NAME][0], entity[self.ANNO_CHECKED_OUT_BY_ID][0]))
                print('Checked out on: {0}'.format(
                    entity[self.ANNO_CHECKED_OUT_DATE][0]))
        else:
            print('No checked out entities found.')

    def checkout(self, checkout_path=os.getcwd(), skip_sync=False, force=False):
        """
        Checks out an Entity.
        """
        print('Checking out...')
        if (not self._load()):
            return

        if (self._is_checked_out(self._entity)):
            if (force):
                print('WARNING: Entity already checked out.')
            else:
                print('Entity already checked out. Aborting.')
                return

        checked_out_parent = self._any_parents_checked_out()
        if (checked_out_parent != None):
            if (force):
                print('WARNING: Parent: {0} ({1}) is checked out.'.format(
                    checked_out_parent.name, checked_out_parent.id))
            else:
                print('Parent: {0} ({1}) is checked out. Aborting.'.format(
                    checked_out_parent.name, checked_out_parent.id))
                return

        checked_out_child = self._any_children_checked_out()
        if (checked_out_child != None):
            if (force):
                print('WANRING: Child: {0} ({1}) is checked out.'.format(
                    checked_out_child.name, checked_out_child.id))
            else:
                print('Child: {0} ({1}) is checked out. Aborting.'.format(
                    checked_out_child.name, checked_out_child.id))
                return

        if (not skip_sync):
            # Download all the folders and files.
            entities = synapseutils.syncFromSynapse(
                self._synapse_client, self._entity, path=checkout_path)
            print('')
            print('Checked out files:')
            for f in entities:
                print('  - {0}'.format(f.path))

            # Write the Synapse ID of the checked out object so we can easily get it for check-in.
            Syt.write_dot_syt(checkout_path, self._entity.id)

        self._entity[self.ANNO_CHECKED_OUT_BY_ID] = self._user.ownerId
        self._entity[self.ANNO_CHECKED_OUT_BY_NAME] = self._user.userName
        self._entity[self.ANNO_CHECKED_OUT_DATE] = datetime.datetime.now()
        self._entity[self.ANNO_CHECKED_OUT_ETAG] = self._entity.etag
        self._synapse_client.store(self._entity)

        print('Check-out was successful')

    def checkin(self, checkout_path=os.getcwd(), skip_sync=False, force=False):
        """
        Checks in an Entity.
        """
        print('Checking in...')
        if (not self._load()):
            return

        if (not self._is_checked_out(self._entity)):
            if (force):
                print('WARNING: Entity not checked out.')
            else:
                print('Entity not checked out. Aborting.')
                return

        if (not force and self._entity[self.ANNO_CHECKED_OUT_BY_ID][0] != self._user.ownerId):
            if (force):
                print('WARNING: Entity is currently checked out by another user.')
            else:
                print(
                    'Entity can only be checked in by the user that checked it out. Aborting.')
                return

        # Upload the files
        if (not skip_sync):
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

    def _any_parents_checked_out(self):
        """
        Gets if any parent entities are checked out.
        """
        parents = self._get_parents(self._entity, [Project, Folder])
        for folder in parents:
            if (self._is_checked_out(folder)):
                return folder

    def _any_children_checked_out(self):
        """
        Gets if any child entities are checked out.
        """
        children = self._get_children(self._entity)
        for folder in children:
            if (self._is_checked_out(folder)):
                return folder

    def _get_parents(self, child_entity, parent_types=[Project]):
        """
        Gets all the parent entities of a specific type.
        """
        results = []

        parent_id = child_entity.parentId

        if (parent_id == None or isinstance(child_entity, Project)):
            return results

        parent = self._synapse_client.get(parent_id)

        for parent_type in parent_types:
            if (isinstance(parent, parent_type)):
                results.append(parent)

        results += self._get_parents(parent, parent_types)

        return results

    def _get_children(self, parent_entity):
        """
        Get all the child Folders and Files.
        """
        results = []

        children = self._synapse_client.getChildren(
            parent_entity, includeTypes=['folder', 'file'])

        for child in children:
            child_entity = self._synapse_client.get(
                child['id'], downloadFile=False)
            results.append(child_entity)
            results += self._get_children(child_entity)

        return results

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
                self._project = self._get_parents(self._entity, [Project])[0]
                print('{0} "{1}" ({2}) from Project "{3}" ({4})'.format(
                    type, self._entity.name, self._entity.id, self._project.name, self._project.id))
        else:
            print('Found {0} {1} ({2})'.format(
                type, self._entity.name, self._entity.id))
            print('Only Projects, Folders, and Files can be checked in/out. Aborting.')
            self._entity = None
            self._project = None

        return self._project != None

    def synapse_login(self):
        """
        Logs into Synapse.
        """
        print('Logging into Synapse...')
        syn_user = os.getenv('SYNAPSE_USER') or self._username
        syn_pass = os.getenv('SYNAPSE_PASSWORD') or self._password

        if syn_user == None:
            syn_user = input('Synapse username: ')

        if syn_pass == None:
            syn_pass = getpass.getpass(prompt='Synapse password: ')

        self._synapse_client = synapseclient.Synapse()
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


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=[
                        'checkout', 'checkin', 'show'], help='The command to execute.')
    parser.add_argument('entity_id', metavar='entity-id', nargs='?',
                        help='The ID of the Synapse Entity to execute the command on.')
    parser.add_argument('checkout_path', metavar='checkout-path',
                        nargs='?', default=os.getcwd(), help='The local path to sync with Synapse.')
    parser.add_argument('-s', '--skip-sync', help='Do not download or upload when checking in/out.',
                        default=False, action='store_true')
    parser.add_argument('-f', '--force', help='Force a check in/out.',
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

    syt = Syt(entity_id, username=args.username, password=args.password)

    if args.command == 'checkin':
        syt.checkin(checkout_path, args.skip_sync, args.force)
    elif args.command == 'checkout':
        syt.checkout(checkout_path, args.skip_sync, args.force)
    else:
        syt.show()


if __name__ == "__main__":
    main(sys.argv[1:])
