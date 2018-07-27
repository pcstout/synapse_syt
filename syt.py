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


class Syt:

    ANNO_CHECKED_OUT_BY_ID = '_syt_by_id'
    ANNO_CHECKED_OUT_BY_NAME = '_syt_by_name'
    ANNO_CHECKED_OUT_DATE = '_syt_date'
    ANNO_CHECKED_OUT_ETAG = '_syt_etag'

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
        self.synapse_login()

        entity = self._synapse_client.get(self._entity_id, downloadFile=False)
        print('{0} ({1})'.format(entity.name, entity.id))

        folders = []

        if (isinstance(entity, Folder)):
            folders.append(entity)

        folders += self._get_children(entity, Folder)

        checked_out = []

        for folder in folders:
            if (self._is_checked_out(folder)):
                checked_out.append(folder)

        if (len(checked_out)):
            for folder in checked_out:
                print('-' * 80)
                print('Entity: {0} ({1})'.format(folder.name, folder.id))
                print('Checked out by: {0} ({1})'.format(
                    folder[self.ANNO_CHECKED_OUT_BY_NAME][0], folder[self.ANNO_CHECKED_OUT_BY_ID][0]))
                print('Checked out on: {0}'.format(
                    folder[self.ANNO_CHECKED_OUT_DATE][0]))
        else:
            print('No checked out entities found.')

    def checkout(self):
        """
        Checks out an Entity.
        """
        print('Checking out...')
        if (not self._load()):
            return

        if (self._is_checked_out(self._entity)):
            print('Entity already checked out. Aborting.')
            return

        checked_out_parent = self._any_parents_checked_out()
        if (checked_out_parent != None):
            print('Parent: {0} ({1}) is checked out. Aborting.'.format(
                checked_out_parent.name, checked_out_parent.id))
            return

        checked_out_child = self._any_children_checked_out()
        if (checked_out_child != None):
            print('Child: {0} ({1}) is checked out. Aborting.'.format(
                checked_out_child.name, checked_out_child.id))
            return

        self._entity[self.ANNO_CHECKED_OUT_BY_ID] = self._user.ownerId
        self._entity[self.ANNO_CHECKED_OUT_BY_NAME] = self._user.userName
        self._entity[self.ANNO_CHECKED_OUT_DATE] = datetime.datetime.now()
        self._entity[self.ANNO_CHECKED_OUT_ETAG] = self._entity.etag
        self._synapse_client.store(self._entity)
        print('Check-out was successful')

    def checkin(self, force=False):
        """
        Checks in an Entity.
        """
        print('Checking in...')
        if (not self._load()):
            return

        if (not self._is_checked_out(self._entity)):
            print('Entity not checked out. Aborting.')
            return

        if (not force and self._entity[self.ANNO_CHECKED_OUT_BY_ID][0] != self._user.ownerId):
            print(
                'Entity can only be checked in by the user that checked it out. Aborting.')
            return

        for key in [self.ANNO_CHECKED_OUT_BY_ID, self.ANNO_CHECKED_OUT_BY_NAME, self.ANNO_CHECKED_OUT_DATE, self.ANNO_CHECKED_OUT_ETAG]:
            if key in self._entity.annotations:
                del self._entity.annotations[key]

        self._synapse_client.store(self._entity)
        print('Check-in was successful')

    def _is_checked_out(self, entity):
        return self.ANNO_CHECKED_OUT_BY_ID in entity

    def _any_parents_checked_out(self):
        parents = self._get_parents(self._entity, parent_type=Folder)
        for folder in parents:
            if (self._is_checked_out(folder)):
                return folder

    def _any_children_checked_out(self):
        children = self._get_children(self._entity, child_type=Folder)
        for folder in children:
            if (self._is_checked_out(folder)):
                return folder

    def _get_parents(self, child_entity, parent_type=Project):
        """
        Gets all the parent entities of a specific type
        """
        parent_id = child_entity.parentId

        if (parent_id == None):
            return None

        results = []

        parent = self._synapse_client.get(parent_id)

        if (isinstance(parent, parent_type)):
            results.append(parent)

        # Do not go past the Project level.
        if (parent.parentId and not isinstance(parent, Project)):
            results += self._get_parents(parent, parent_type)

        return results

    def _get_children(self, parent_entity, child_type=Folder):
        """
        Get all the child entities of a specific type
        """
        results = []

        child_type_str = child_type._synapse_entity_type.split('.')[-1].lower()

        children = self._synapse_client.getChildren(
            parent_entity, includeTypes=[child_type_str])

        for child in children:
            child_entity = self._synapse_client.get(
                child['id'], downloadFile=False)
            results.append(child_entity)
            results += self._get_children(child_entity, child_type)

        return results

    def _load_entity(self):
        """
        Loads the Entity and its Project.
        """
        print('Loading Entity...')
        self._entity = self._synapse_client.get(
            self._entity_id, downloadFile=False)

        type = self._entity.entityType.split('.')[-1].replace('Entity', '')

        if type in ['Folder']:
            print('Loading Project...')
            self._project = self._get_parents(self._entity, Project)[0]
            print('{0} {1} ({2}) from Project {3} ({4})'.format(
                type, self._entity.name, self._entity.id, self._project.name, self._project.id))
        else:
            print('Found {0} {1} ({2})'.format(
                type, self._entity.name, self._entity.id))
            print('Only Folders can be checked in/out. Aborting.')
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


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=[
                        'checkout', 'checkin', 'show'], help='The command to execute.')
    parser.add_argument('entity_id', metavar='entity-id',
                        help='The ID of the Synapse Folder to execute the command on. Can be a Project ID for the show command.')
    parser.add_argument(
        '-f', '--force', help='Force a check-in.', default=False, action='store_true')
    parser.add_argument('-u', '--username',
                        help='Synapse username.', default=None)
    parser.add_argument('-p', '--password',
                        help='Synapse password.', default=None)
    args = parser.parse_args()

    syt = Syt(args.entity_id, username=args.username, password=args.password)

    if args.command == 'checkin':
        syt.checkin(force=args.force)
    elif args.command == 'checkout':
        syt.checkout()
    else:
        syt.show()


if __name__ == "__main__":
    main(sys.argv[1:])
