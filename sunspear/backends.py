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
import riak

from itertools import groupby

from sunspear.activitystreams.models import Object, Activity
from sunspear.lib.dotdict import dotdictify

from riak import RiakPbcTransport


class RiakBackend(object):
    def __init__(self, settings, **kwargs):

        self._riak_backend = riak.RiakClient(host="127.0.0.1", port=8081,\
            transport_class=RiakPbcTransport, transport_options={"max_attempts": 2})

        self._streams = self._riak_backend.bucket("streams")
        self._followers = self._riak_backend.bucket("followers")
        self._objects = self._riak_backend.bucket("objects")
        self._activities = self._riak_backend.bucket("activities")

    def create_object(self, object_dict):
        obj = Object(object_dict, bucket=self._objects)
        obj.save()

        return obj.get_riak_object()

    def create_activity(self, actstream_dict):
        activity_obj = Activity(actstream_dict, bucket=self._activities, objects_bucket=self._objects)
        activity_obj.save()

        return activity_obj.get_riak_object()

    def create_stream(self, name):
        stream_id = self._get_new_uuid()
        stream_obj = Object({
            "id": stream_id,
            "displayName": name,
            "published": datetime.datetime.utcnow(),
        }, bucket=self._streams)
        stream_obj.save()
        return stream_obj.get_riak_object()

    def get_activities(self, activity_ids=[], groupby_list=[]):
        if not activity_ids:
            return []
        activity_buckey_name = self._activities.get_name()
        activities = self._riak_backend

        for activity_id in activity_ids:
            activities = activities.add(activity_buckey_name, str(activity_id))

        activities = activities.map("Riak.mapValuesJson").run()

        _raw_group_actvities = groupby(activities, self._group_by_aggregator(groupby_list))

    def _compress_activities(self, group_by_attributes=[], grouped_activities=[]):
        grouped_activities_list = []
        for keys, group in grouped_activities:
            group_list = list(group)
            #special case. If we just grouped one activity, we don't need to aggregate
            if len(group_list) == 1:
                grouped_activities_list.append(group_list[0])
            else:
                nested_root_attributes = []
                #we have sevral activities that can be grouped together
                aggregated_activity = dotdictify({'grouped_by_values': keys})
                aggregated_activity.update(group_list[0])

                #special handeling if we are grouping by a nested attribute
                #In this case, we listify all the other keys
                for attr in group_by_attributes:
                    if '.' in attr:
                        nested_val = aggregated_activity.get(attr)
                        if nested_val is not None and isinstance(nested_val, dict):
                            nested_dict, attr = attr.rsplit('.', 1)
                            nested_root, rest = attr.split('.', 1)

                            for nested_dict_key, nested_dict_value in aggregated_activity.get(nested_dict).items():
                                if nested_dict_key != attr:
                                    aggregated_activity['.'.join([nested_dict, nested_dict_key])] = [nested_dict_value]

                #now we listify all other non nested attributes
                for key, val in aggregated_activity.items():
                    if key not in group_by_attributes and key not in nested_root_attributes:
                        aggregated_activity[key] = [val]



    def _group_by_aggregator(self, group_by_attributes=[]):
        def _callback(activity):
            activity_dict = dotdictify(activity)
            matching_attributes = []

            for attribute in group_by_attributes:
                value = activity_dict.get(attribute)
                if activity_dict.get(attribute) is not None:
                    matching_attributes.append(value)
            return matching_attributes
        return _callback

    def _get_new_uuid(self):
        return uuid.uuid1().hex

    def _get_riak_client(self):
        return self._riak_backend
