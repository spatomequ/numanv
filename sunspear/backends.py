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

from sunspear.activitystreams.models import Object, Activity, Model, ReplyActivity, LikeActivity

from nydus.db import create_cluster

from riak import RiakPbcTransport

import uuid
import riak
import copy

JS_MAP = """
    function(value, keyData, arg) {
      if (value["not_found"]) {
        return [value];
      }
      var newValues = Riak.mapValues(value, keyData, arg);
      newValues = newValues.map(function(nv) {
        try {
            var parsedNv = JSON.parse(nv); parsedNv["timestamp"] = value.values[0].metadata.index.timestamp_int; return parsedNv;
        } catch(e) {
            return;
        }
      });
      //filter out undefinded things
      return newValues.filter(function(value){ return value; });
    }
"""

JS_REDUCE_FILTER_PROP = """
    function(value, arg) {
        if (arg['raw_filter'] != "") {
            raw_filter = eval(arg['raw_filter']);
            return value.filter(raw_filter);
        }
        return value.filter(function(obj){
            for (var filter in arg['filters']){
                if (filter in obj) {
                    for(var i in arg['filters'][filter]) {
                        if (obj[filter] == arg['filters'][filter][i]) {
                            return true;
                        }
                    }
                }
            }
            return false;
        });
    }
"""

JS_REDUCE_FILTER_AUD_TARGETTING = """
    function(value, arg) {
        var audience_targeting = ['to', 'bto', 'cc', 'bcc'];
        return value.filter(function(obj){
            if (arg['public'] && audience_targeting.reduce(function(prev, next){ return prev && !(next in obj) }, true)) {
                return true;
            }
            for (var i in audience_targeting){
                var targeting_field = audience_targeting[i];
                if (targeting_field in obj && targeting_field in arg['filters']) {
                    for(var j in arg['filters'][targeting_field]) {
                        return obj[targeting_field].indexOf(arg['filters'][targeting_field][j]) != -1;
                    }
                }
            }
            return false;
        });
    }
"""

JS_REDUCE = """
    function(value, arg) {
      var sortFunc = function(x,y) {
        if(x["timestamp"] == y["timestamp"]) return 0;
        return x["timestamp"] > y["timestamp"] ? 1 : -1;
      }
      var newValues = Riak.filterNotFound(value);
      return newValues.sort(sortFunc);
    }
"""

JS_REDUCE_OBJS = """
    function(value, arg) {
      return Riak.filterNotFound(value);
    }
"""


class RiakBackend(object):
    def __init__(self, host_list=[], defaults={}, **kwargs):

        sunspear_defaults = {
         'transport_options': {"max_attempts": 4},
         'transport_class': RiakPbcTransport,
        }

        sunspear_defaults.update(defaults)

        hosts = {}
        for i, host_settings in enumerate(host_list):
            hosts[i] = host_settings

        self._riak_backend = create_cluster({
            'engine': 'nydus.db.backends.riak.Riak',
            'defaults': sunspear_defaults,
            'router': 'nydus.db.routers.keyvalue.PartitionRouter',
            'hosts': hosts,
        })

        self._objects = self._riak_backend.bucket("objects")
        self._activities = self._riak_backend.bucket("activities")

    def clear_all(self):
        """
        Deletes all activity stream data from riak
        """
        self.clear_all_activities()
        self.clear_all_objects()

    def clear_all_objects(self):
        """
        Deletes all objects data from riak
        """
        for key in self._objects.get_keys():
            self._objects.get(key).delete(rw='all', r='all', w='all', dw='all')
            assert not self._objects.get(key).exists()

    def clear_all_activities(self):
        """
        Deletes all activities data from riak
        """
        for key in self._activities.get_keys():
            self._activities.get(key).delete(rw='all', r='all', w='all', dw='all')
            assert not self._activities.get(key).exists()

    def create_object(self, object_dict):
        """
        Creates an object that can be used as part of an activity. If you specific and object with an id
        that already exists, that object is overriden
        """
        obj = Object(object_dict, bucket=self._objects)
        riak_object = obj.save()

        return riak_object.get_data()

    def create_activity(self, actstream_dict):
        """
        Creates an activity. You can provide objects for activities as dictionaries or as ids for already
        existing objects. If you provide a dictionary for an object, it is saved as a new object. If you provide
        an object id and the object does not exist, it is saved anyway, and returned as an empty dictionary when
        retriving the activity.
        """
        activity_obj = Activity(actstream_dict, bucket=self._activities, objects_bucket=self._objects)
        riak_object = activity_obj.save()

        return self.dehydrate_activities([riak_object.get_data()])[0]

    def create_reply(self, activity_id, actor, reply, extra={}):
        """
        Creates a ``reply`` for an activity.

        :type activity_id: int
        :param activity_id: The id of the activity we want to create a reply for
        """
        activity = Activity({}, bucket=self._activities, objects_bucket=self._objects)
        activity.get(key=activity_id)

        reply_activity, activity = activity.create_reply(actor, reply, extra=extra)
        dehydrated_activities = self.dehydrate_activities([reply_activity.get_data(), activity.get_data()])
        return dehydrated_activities[0], dehydrated_activities[1]

    def create_like(self, activity_id, actor, extra={}):
        """
        Creates a ``like`` for an activity.

        :type activity_id: string
        :param activity_id: The id of the activity we want to create a reply for
        """
        activity = Activity({}, bucket=self._activities, objects_bucket=self._objects)
        activity.get(key=activity_id)

        like_activity, activity = activity.create_like(actor, extra=extra)
        dehydrated_activities = self.dehydrate_activities([like_activity.get_data(), activity.get_data()])
        return dehydrated_activities[0], dehydrated_activities[1]

    def delete(self, activity_id):
        """
        Deletes an activity item and all associated sub items

        :type activity_id: string
        :param activity_id: The id of the activity we want to create a reply for
        """
        activity = Activity({}, bucket=self._activities, objects_bucket=self._objects)
        activity.get(key=activity_id)
        activity.delete()

    def delete_reply(self, reply_id):
        """
        Deletes a ``reply`` made on an activity. This will also update the corresponding activity.

        :type reply_id: string
        :param reply_id: the id of the reply activity to delete.
        """
        reply = ReplyActivity({}, bucket=self._activities, objects_bucket=self._objects)
        riak_object = reply.delete(key=reply_id)
        return self.dehydrate_activities([riak_object.get_data()])[0]

    def delete_like(self, like_id):
        """
        Deletes a ``like`` made on an activity. This will also update the corresponding activity.

        :type like_id: string
        :param like_id: the id of the like activity to delete.
        """
        like = LikeActivity({}, bucket=self._activities, objects_bucket=self._objects)
        riak_object = like.delete(key=like_id)
        return self.dehydrate_activities([riak_object.get_data()])[0]

    def get_objects(self, object_ids=[]):
        """
        Gets a list of objects.

        :type object_ids: list
        :param object_ids: a list of objects
        """
        return self._get_many_objects(object_ids)

    def get_activities(self, activity_ids=[], raw_filter="", filters={}, include_public=False, \
        audience_targeting={}, aggregation_pipeline=[]):
        """
        Gets a list of activities. You can also group activities by providing a list of attributes to group
        by.

        :type activity_ids: list
        :param activity_ids: The list of activities you want to retrieve
        :type filters: dict
        :param filters: filters list of activities by key, value pair. For example, ``{'verb': 'comment'}`` would only return activities where the ``verb`` was ``comment``.
        Filters do not work for nested dictionaries.
        :type raw_filter: string
        :param raw_filter: allows you to specify a javascript function as a string. The function should return ``true`` if the activity should be included in the result set
        or ``false`` it shouldn't. If you specify a raw filter, the filters specified in ``filters`` will not run. How ever, the results will still be filtered based on
        the ``audience_targeting`` parameter.
        :type include_public: boolean
        :param include_public: If ``True``, and the ``audience_targeting`` dictionary is defined, activities that are
        not targeted towards anyone are included in the results
        :type audience_targeting: dict
        :param audience_targeting: Filters the list of activities targeted towards a particular audience. The key for the dictionary is one of ``to``, ``cc``, ``bto``, or ``bcc``.
        The values are an array of object ids
        :type aggregation_pipeline: array of ``sunspear.aggregators.base.BaseAggregator``
        :param aggregation_pipeline: modify the final list of activities. Exact results depends on the implementation of the aggregation pipeline
        """
        if not activity_ids:
            return []

        activities = self._get_many_activities(activity_ids, raw_filter=raw_filter, filters=filters, include_public=include_public, \
            audience_targeting=audience_targeting)

        activities = self.dehydrate_activities(activities)
        original_activities = copy.deepcopy(activities)

        for aggregator in aggregation_pipeline:
            activities = aggregator.process(activities, original_activities, aggregation_pipeline)
        return activities

    def dehydrate_activities(self, activities):
        """
        Takes a raw list of activities returned from riak and replace keys with contain ids for riak objects with actual riak object
        """
        activities = self._extract_sub_activities(activities)

        #collect a list of unique object ids. We only iterate through the fields that we know
        #for sure are objects. User is responsible for hydrating all other fields.
        object_ids = set()
        for activity in activities:
            object_ids.update(self._extract_object_keys(activity))

        #Get the objects for the ids we have collected
        objects = self._get_many_objects(object_ids)
        objects_dict = dict(((obj["id"], obj,) for obj in objects))

        #We also need to extract any activities that were diguised as objects. IE activities with
        #objectType=activity
        activities_in_objects_ids = set()

        #replace the object ids with the hydrated objects
        for activity in activities:
            activity = self._dehydrate_object_keys(activity, objects_dict)
            #Extract keys of any activities that were objects
            activities_in_objects_ids.update(self._extract_activity_keys(activity, skip_sub_activities=True))

        #If we did have activities that were objects, we need to hydrate those activities and
        #the objects for those activities
        if activities_in_objects_ids:
            sub_activities = self._get_many_activities(activities_in_objects_ids)
            activities_in_objects_dict = dict(((sub_activity["id"], sub_activity,) for sub_activity in sub_activities))
            for activity in activities:
                activity = self._dehydrate_sub_activity(activity, activities_in_objects_dict, skip_sub_activities=True)

                #we have to do one more round of object dehydration for our new sub-activities
                object_ids.update(self._extract_object_keys(activity))

            #now get all the objects we don't already have and for sub-activities and and hydrate them into
            #our list of activities
            object_ids -= set(objects_dict.keys())
            objects = self._get_many_objects(object_ids)
            for obj in objects:
                objects_dict[obj["id"]] = obj

            for activity in activities:
                activity = self._dehydrate_object_keys(activity, objects_dict)

        return activities

    def _extract_sub_activities(self, activities):
        """
        Extract all objects that have an objectType of activity as an activity
        """
        #We might also have to get sub activities for things like replies and likes
        activity_ids = set()
        activities_dict = dict(((activity["id"], activity,) for activity in activities))

        for activity in activities:
            activity_ids.update(self._extract_activity_keys(activity))

        if activity_ids:
            #don't bother fetching the activities we already have
            activity_ids -= set(activities_dict.keys())
            if activity_ids:
                sub_activities = self._get_many_activities(activity_ids)
                for sub_activity in sub_activities:
                    activities_dict[sub_activity["id"]] = sub_activity

            #Dehydrate out any subactivities we may have
            for activity in activities:
                activity = self._dehydrate_sub_activity(activity, activities_dict)

        return activities

    def _extract_activity_keys(self, activity, skip_sub_activities=False):
        keys = []
        for activity_key in Model._object_fields + ['inReplyTo']:
            if activity_key not in activity:
                continue
            obj = activity.get(activity_key)
            if isinstance(obj, dict):
                if obj.get('objectType', None) == 'activity':
                    keys.append(obj['id'])
                if obj.get('inReplyTo', None):
                    [keys.append(in_reply_to_obj['id']) for in_reply_to_obj in obj['inReplyTo']]

        if not skip_sub_activities:
            for collection in Activity._response_fields:
                if collection in activity and activity[collection]['items']:
                    for item in activity[collection]['items']:
                        keys.extend(self._extract_activity_keys(item))
        return keys

    def _dehydrate_sub_activity(self, sub_activity, obj_list, skip_sub_activities=False):
        for activity_key in Model._object_fields:
            if activity_key not in sub_activity:
                continue
            if isinstance(sub_activity[activity_key], dict):
                if sub_activity[activity_key].get('objectType', None) == 'activity':
                    sub_activity[activity_key].update(obj_list[sub_activity[activity_key]['id']])
                if sub_activity[activity_key].get('inReplyTo', None):
                    for i, in_reply_to_obj in enumerate(sub_activity[activity_key]['inReplyTo']):
                        sub_activity[activity_key]['inReplyTo'][i]\
                            .update(obj_list[sub_activity[activity_key]['inReplyTo'][i]['id']])

        if not skip_sub_activities:
            for collection in Activity._response_fields:
                if collection in sub_activity and sub_activity[collection]['items']:
                    for i, item in enumerate(sub_activity[collection]['items']):
                        sub_activity[collection]['items'][i] = self._dehydrate_sub_activity(item, obj_list)

        return sub_activity

    def _extract_object_keys(self, activity, skip_sub_activities=False):
        keys = []
        for object_key in Model._object_fields + Activity._direct_audience_targeting_fields \
            + Activity._indirect_audience_targeting_fields:
            if object_key not in activity:
                continue
            objects = activity.get(object_key)
            if isinstance(objects, dict):
                if objects.get('objectType', None) == 'activity':
                    keys = keys + self._extract_object_keys(objects)
                if objects.get('inReplyTo', None):
                    [keys.extend(self._extract_object_keys(in_reply_to_obj, skip_sub_activities=skip_sub_activities)) \
                        for in_reply_to_obj in objects['inReplyTo']]
            if isinstance(objects, list):
                for item in objects:
                    if isinstance(item, basestring):
                        keys.append(item)
            if isinstance(objects, basestring):
                keys.append(objects)

        if not skip_sub_activities:
            for collection in Activity._response_fields:
                if collection in activity and activity[collection]['items']:
                    for item in activity[collection]['items']:
                        keys.extend(self._extract_object_keys(item))
        return keys

    def _dehydrate_object_keys(self, activity, objects_dict, skip_sub_activities=False):
        for object_key in Model._object_fields + Activity._direct_audience_targeting_fields \
            + Activity._indirect_audience_targeting_fields:
            if object_key not in activity:
                continue
            activity_objects = activity.get(object_key)
            if isinstance(activity_objects, dict):
                if activity_objects.get('objectType', None) == 'activity':
                    activity[object_key] = self._dehydrate_object_keys(activity_objects, objects_dict, skip_sub_activities=skip_sub_activities)
                if activity_objects.get('inReplyTo', None):
                    for i, in_reply_to_obj in enumerate(activity_objects['inReplyTo']):
                        activity_objects['inReplyTo'][i] = \
                            self._dehydrate_object_keys(activity_objects['inReplyTo'][i], \
                                objects_dict, skip_sub_activities=skip_sub_activities)
            if isinstance(activity_objects, list):
                for i, obj_id in enumerate(activity_objects):
                    if isinstance(activity[object_key][i], basestring):
                        activity[object_key][i] = objects_dict.get(obj_id, {})
            if isinstance(activity_objects, basestring):
                activity[object_key] = objects_dict.get(activity_objects, {})

        if not skip_sub_activities:
            for collection in Activity._response_fields:
                if collection in activity and activity[collection]['items']:
                    for i, item in enumerate(activity[collection]['items']):
                        activity[collection]['items'][i] = self._dehydrate_object_keys(item, objects_dict)
        return activity

    def _get_many_objects(self, object_ids):
        """
        Given a list of object ids, returns a list of objects
        """
        if not object_ids:
            return object_ids
        object_bucket_name = self._objects.get_name()
        objects = self._riak_backend

        for object_id in object_ids:
            objects = objects.add(object_bucket_name, str(object_id))

        results = objects.map("Riak.mapValuesJson").reduce(JS_REDUCE_OBJS).run()
        return results or []

    def _get_many_activities(self, activity_ids=[], raw_filter="", filters={}, include_public=False, audience_targeting={}):
        """
        Given a list of activity ids, returns a list of activities from riak.

        :type activity_ids: list
        :param activity_ids: The list of activities you want to retrieve
        :type raw_filter: string
        :param raw_filter: allows you to specify a javascript function as a string. The function should return ``true`` if the activity should be included in the result set
        or ``false`` it shouldn't. If you specify a raw filter, the filters specified in ``filters`` will not run. How ever, the results will still be filtered based on
        the ``audience_targeting`` parameter.
        :type filters: dict
        :param filters: filters list of activities by key, value pair. For example, ``{'verb': 'comment'}`` would only return activities where the ``verb`` was ``comment``.
        Filters do not work for nested dictionaries.
        :type include_public: boolean
        :param include_public: If ``True``, and the ``audience_targeting`` dictionary is defined, activities that are
        not targeted towards anyone are included in the results
        :type audience_targeting: dict
        :param audience_targeting: Filters the list of activities targeted towards a particular audience. The key for the dictionary is one of ``to``, ``cc``, ``bto``, or ``bcc``.
        """
        activity_bucket_name = self._activities.get_name()
        activities = self._riak_backend

        for activity_id in activity_ids:
            activities = activities.add(activity_bucket_name, str(activity_id))

        results = activities.map(JS_MAP)

        if audience_targeting:
            results = results.reduce(JS_REDUCE_FILTER_AUD_TARGETTING, options={'arg': {'public': include_public, 'filters': audience_targeting}})

        if filters or raw_filter:
            results = results.reduce(JS_REDUCE_FILTER_PROP, options={'arg': {'raw_filter': raw_filter, 'filters': filters}})

        results = results.reduce(JS_REDUCE).run()
        results = results or []

        #riak does not return the results in any particular order (unless we sort). So,
        #we have to put the objects returned by riak back in order
        results_map = dict(map(lambda result: (result['id'], result,), results))
        reordered_results = [results_map[id] for id in activity_ids if id in results_map]

        return reordered_results

    def _get_new_uuid(self):
        return uuid.uuid1().hex

    def _get_riak_client(self):
        return self._riak_backend
