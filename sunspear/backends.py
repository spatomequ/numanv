"""
Copyright 2012 Numan Sachwani <numan856@gmail.com>

This file is provided to you under the Apache License,
Version 2.0 (the "License"); you may not use this file
except in compliance with the License.  You may obtain
a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
"""
import uuid
import datetime

from nydus.db import create_cluster
from sunspear.activitystreams.models import Object


class RiakBackend(object):
    def __init__(self, settings, **kwargs):
        nydus_hosts = {}

        hosts = settings.get("hosts", [])
        if not hosts:
            raise Exception("No redis hosts specified")

        for i, host in enumerate(hosts):
            nydus_hosts[i] = host

        defaults = settings.get("defaults",
            {
                'prefix': 'riak',
                'mapred_prefix': "mapred",
                'port': 8098,
            })

        self._riak_backend = create_cluster({
            'engine': 'nydus.db.backends.riak.Riak',
            'router': 'nydus.db.routers.RoundRobinRouter',
            'hosts': nydus_hosts,
            'defaults': defaults,
        })

        self._streams = self._riak_backend.bucket("streams")
        self._followers = self._riak_backend.bucket("followers")
        self._objects = self._riak_backend.bucket("objects")

    def _get_new_uuid(self):
        return uuid.uuid1().hex

    def create_object(self, object_dict):
        obj = Object(object_dict)
        riak_obj = self._objects.new()
        obj.save(riak_obj)

        return riak_obj

    def create_stream(self, name):
        stream_id = self._get_new_uuid()
        stream_obj = Object({
            "id": stream_id,
            "displayName": name,
            "published": datetime.datetime.utcnow(),
        })
        riak_obj = self._streams.new(stream_id)
        stream_obj.save(riak_obj)
        return riak_obj

    def _get_riak_client(self):
        return self._riak_backend
