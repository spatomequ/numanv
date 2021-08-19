from sunspear.exceptions import (SunspearValidationException, SunspearInvalidConfigurationError,
    SunspearNotFoundException, SunspearRiakException)
from sunspear.lib.rfc3339 import rfc3339

from dateutil.parser import parse

import uuid
import datetime
import calendar


class Model(object):
    _required_fields = []
    _media_fields = []
    _reserved_fields = []
    _object_fields = ['actor', 'generator', 'object', 'provider', 'target', 'author']
    _datetime_fields = ['published', 'updated']
    _response_fields = []
    _direct_audience_targeting_fields = []
    _indirect_audience_targeting_fields = []

    def __init__(self, object_dict, bucket=None, riak_object=None, *args, **kwargs):
        self._riak_object = riak_object
        self._bucket = bucket
        self._dict = self.objectify_dict(object_dict)
        self._set_defaults()

    def _set_defaults(self):
        if 'id' in self._dict:
            self._dict['id'] = str(self._dict['id'])

    def objectify_dict(self, object_dict):
        _dict = {}
        for key, value in object_dict.iteritems():
            if key in self._media_fields and isinstance(value, dict):
                _dict[key] = MediaLink(value)
            elif key in self._object_fields and key not in self._response_fields and isinstance(value, dict):
                _dict[key] = Object(value)
            elif key in self._direct_audience_targeting_fields:
                _dict[key] = [Object(target_obj) if isinstance(target_obj, dict) else target_obj for target_obj in value]
            elif key in self._indirect_audience_targeting_fields:
                _dict[key] = [Object(target_obj) if isinstance(target_obj, dict) else target_obj for target_obj in value]
            else:
                _dict[key] = value
        return _dict

    def validate(self):
        for field in self._required_fields:
            if not self._dict.get(field, None):
                raise SunspearValidationException("Required field missing: %s" % field)

        for field in self._reserved_fields:
            if (self._riak_object is None or \
                not self._riak_object.exists()) and self._dict.get(field, None) is not None:
                raise SunspearValidationException("Reserved field name used: %s" % field)

        for field in self._media_fields:
            if self._dict.get(field, None) and isinstance(self._dict.get(field, None), Model):
                self._dict.get(field).validate()

        for field in self._object_fields:
            if self._dict.get(field, None) and isinstance(self._dict.get(field, None), Model):
                self._dict.get(field).validate()

        for field in self._direct_audience_targeting_fields + self._indirect_audience_targeting_fields:
            if self._dict.get(field, None):
                for sub_obj in self._dict.get(field):
                    if sub_obj and isinstance(sub_obj, Model):
                        sub_obj.validate()

    def parse_data(self, data, *args, **kwargs):
        #TODO Rename to jsonify_dict
        _parsed_data = data.copy()

        #parse datetime fields
        for d in self._datetime_fields:
            if d in _parsed_data and _parsed_data[d]:
                _parsed_data[d] = self._parse_date(_parsed_data[d], utc=True, use_system_timezone=False)

        #parse object fields
        for c in self._object_fields:
            if c in _parsed_data and _parsed_data[c] and isinstance(_parsed_data[c], Model):
                _parsed_data[c] = _parsed_data[c].parse_data(_parsed_data[c].get_dict())

        #parse direct and indirect audience targeting
        for c in self._indirect_audience_targeting_fields + self._direct_audience_targeting_fields:
            if c in _parsed_data and _parsed_data[c]:
                _parsed_data[c] = [obj.parse_data(obj.get_dict()) if isinstance(obj, Model) else obj\
                    for obj in _parsed_data[c]]

        #parse media fields
        for c in self._media_fields:
            if c in _parsed_data and _parsed_data[c] and isinstance(_parsed_data[c], Model):
                _parsed_data[c] = _parsed_data[c].parse_data(_parsed_data[c].get_dict())

        #parse anything that is a dictionary for things like datetime fields that are datetime objects
        for k, v in _parsed_data.items():
            if isinstance(v, dict) and k not in self._response_fields:
                _parsed_data[k] = self.parse_data(v)

        return _parsed_data

    def set_indexes(self, riak_object):
        #TODO: Need tests for this
        riak_object.add_index("timestamp_int", self._get_timestamp())
        return riak_object

    def save(self, *args, **kwargs):
        if self._bucket is None:
            raise SunspearInvalidConfigurationError("You must pass a riak bucket in the constructor.")

        if self._riak_object is None:
            _riak_object = self._bucket.new(key=self._dict["id"])
            self._riak_object = _riak_object
        else:
            _riak_object = self._riak_object

        self.validate()
        self.riak_validate(*args, **kwargs)

        #we are suppose to maintain our own published and updated fields
        if 'published' in self._reserved_fields and not self._dict.get('published', None):
            self._dict['published'] = datetime.datetime.utcnow()
        elif 'updated' in self._reserved_fields:
            self._dict['updated'] = datetime.datetime.utcnow()

        parsed_data = self.parse_data(self._dict, *args, **kwargs)

        _riak_object.set_data(parsed_data)
        _riak_object = self.set_indexes(_riak_object)

        _riak_object.store()
        return _riak_object

    def set_bucket(self, bucket):
        self._bucket = bucket

    def get(self, key=None):
        #TODO need tests for this
        if key is None and id is None:
            raise SunspearValidationException("You must provide either ``key`` or ``id`` to get an object.")
        key = str(key)

        riak_obj = self._bucket.get(key)
        if not riak_obj.exists():
            raise SunspearNotFoundException("Could not find the object by ``key`` or ``id`")
        self._riak_object = riak_obj
        self._dict = self.objectify_dict(self._riak_object.get_data())

        self._set_defaults()

    def _get_keys_by_index(self, index_name='clientid_bin', index_value=""):
        client = self._riak_object._client
        result = client.index(self._riak_object.get_bucket().get_name(), index_name, index_value).run()
        return result

    def get_riak_object(self):
        return self._riak_object

    def get_dict(self):
        return self._dict

    def riak_validate(self):
        return True

    def _parse_date(self, date=None, utc=True, use_system_timezone=False):
        dt = None
        if date is None or not isinstance(date, datetime.datetime):
            if isinstance(date, basestring):
                try:
                    dt = parse(date)
                except ValueError:
                    dt = datetime.datetime.utcnow()
            else:
                dt = datetime.datetime.utcnow()
        else:
            dt = date
        return rfc3339(dt, utc=utc, use_system_timezone=use_system_timezone)

    def _get_timestamp(self):
        now = datetime.datetime.utcnow()
        return long(str(calendar.timegm(now.timetuple())) + now.strftime("%f"))

    def _get_new_uuid(self):
        return uuid.uuid1().hex

    def __getitem__(self, key):
        return self._dict[key]


class Activity(Model):
    _required_fields = ['verb', 'actor', 'object']
    _media_fields = ['icon']
    _reserved_fields = ['published', 'updated']
    _response_fields = ['replies', 'likes']
    _direct_audience_targeting_fields = ['to', 'bto']
    _indirect_audience_targeting_fields = ['cc', 'bcc']

    def __init__(self, object_dict, *args, **kwargs):
        if 'objects_bucket' not in kwargs:
            raise SunspearInvalidConfigurationError("Riak bucket for ``Object`` not passed.")
        self._objects_bucket = kwargs['objects_bucket']

        super(Activity, self).__init__(object_dict, *args, **kwargs)

    def _set_defaults(self):
        super(Activity, self)._set_defaults()
        if "id" not in self._dict or not self._dict["id"]:
            self._dict["id"] = self._get_new_uuid()

        if 'replies' not in self._dict:
            self._dict['replies'] = {'totalItems': 0, 'items': []}

        if 'likes' not in self._dict:
            self._dict['likes'] = {'totalItems': 0, 'items': []}

    def save(self, *args, **kwargs):
        return_val = None
        #if things in the object field seem like they are new
        objs_created = []
        objs_modified = []
        for key, value in self._dict.items():
            if key in self._object_fields and isinstance(value, Object):
                previous_value = Object(value.get_dict(), bucket=self._objects_bucket)
                try:
                    previous_value.get(previous_value.get_dict().get('id'))
                except:
                    previous_value = None

                value.set_bucket(self._objects_bucket)
                try:
                    if previous_value:
                        objs_modified.append(previous_value)
                        value.save()
                    else:
                        value.save()
                        objs_created.append(value)
                except Exception:
                    self._rollback(objs_created, objs_modified)
                    raise
                    # raise SunspearRiakException('There was an error creating the objects for this activity.')
                self._dict[key] = value.get_dict()["id"]
            if key in self._direct_audience_targeting_fields + self._indirect_audience_targeting_fields\
                and value:
                for i, target_obj in enumerate(value):
                    if isinstance(target_obj, Object):
                        previous_value = Object(target_obj.get_dict(), bucket=self._objects_bucket)
                        try:
                            previous_value.get(previous_value.get_dict().get('id'))
                        except:
                            previous_value = None

                        target_obj.set_bucket(self._objects_bucket)
                        try:
                            if previous_value:
                                objs_modified.append(previous_value)
                                target_obj.save()
                            else:
                                target_obj.save()
                                objs_created.append(value)
                        except Exception:
                            self._rollback(objs_created, objs_modified)
                            raise
                        self._dict[key][i] = target_obj.get_dict()["id"]

        try:
            return_val = super(Activity, self).save(*args, **kwargs)
        except Exception:
            self._rollback(objs_created, objs_modified)
            raise

        return return_val

    def riak_validate(self, update=False, *args, **kwargs):
        #TODO Need tests for this
        if not update and self._bucket.get(self._dict["id"]).exists():
            raise SunspearValidationException("Object with ID already exists")

    def create_reply(self, actor, reply):
        return self._create_activity_subitem(actor, reply, verb="reply", objectType="reply", collection="replies", activityClass=ReplyActivity)

    def create_like(self, actor):
        return self._create_activity_subitem(actor, verb="like", objectType="like", collection="likes", activityClass=LikeActivity)

    def _create_activity_subitem(self, actor, content="", verb="reply", objectType="reply", collection="replies", activityClass=None):
        in_reply_to_dict = {
            'objectType': 'activity',
            'displayName': self._dict['verb'],
            'id': self._dict['id'],
            'published': self._dict['published']
        }
        reply_obj = {
            'objectType': objectType,
            'id': self._get_new_uuid(),
            'published': datetime.datetime.utcnow(),
            'content': content,
            'inReplyTo': [in_reply_to_dict],
        }

        reply_dict = {
            'actor': actor,
            'object': reply_obj,
            'target': self._dict['id'],
            'activity_author': self._dict['actor'],
            'verb': verb
        }

        if isinstance(content, dict):
            reply_dict['object'].update(content)

        _activity = activityClass(reply_dict, activity_id=self._dict['id'], bucket=self._bucket, objects_bucket=self._objects_bucket)
        _activity.save()

        _activity_data = _activity.get_riak_object().get_data()

        _sub_dict = {
            'actor': _activity_data['actor'],
            'verb': verb,
            'object': {
                'objectType': 'activity',
                'id': _activity_data['id'],
            }
        }

        self._dict[collection]['totalItems'] += 1
        #insert the newest comment at the top of the list
        self._dict[collection]['items'].insert(0, _sub_dict)

        self.save(update=True)

        return _activity._riak_object, self._riak_object

    def set_indexes(self, riak_object):
        super(Activity, self).set_indexes(riak_object)
        #TODO: Need tests for this
        #store a secondary index so we can search by it to check for duplicates
        riak_object.add_index("verb_bin", str(self._dict['verb']))
        riak_object.add_index("actor_bin", str(self._dict['actor']))
        riak_object.add_index("object_bin", str(self._dict['object']))
        if 'target' in self._dict and self._dict.get("target"):
            riak_object.add_index("target_bin", str(self._dict['target']))

        return riak_object

    def parse_data(self, data, *args, **kwargs):
        #TODO Rename to jsonify_dict
        _parsed_data = super(Activity, self).parse_data(data, *args, **kwargs)
        for response_field in self._response_fields:
            if response_field in _parsed_data:
                if not _parsed_data[response_field]['items']:
                    del _parsed_data[response_field]
                else:
                    for i, comment in enumerate(_parsed_data[response_field]['items']):
                        _parsed_data[response_field]['items'][i] = super(Activity, self).parse_data(comment, *args, **kwargs)

        return _parsed_data

    def _rollback(self, new_objects, modified_objects):
        [obj_created.get_riak_object().delete() for obj_created in new_objects]
        [obj_modified.get_riak_object().store() for obj_modified in modified_objects]


class ReplyActivity(Activity):
    def __init__(self, object_dict, *args, **kwargs):

        super(ReplyActivity, self).__init__(object_dict, *args, **kwargs)

        del self._dict['replies']
        del self._dict['likes']
        self._activity_id = kwargs.get('activity_id', None)

    def set_indexes(self, riak_object):
        super(ReplyActivity, self).set_indexes(riak_object)
        #TODO: Need tests for this
        riak_object.add_index("inreplyto_bin", str(self._activity_id))

        return riak_object

    def delete(self, key=None):
        self.get(key=key)
        if self._dict['verb'] != 'reply':
            raise SunspearValidationException("Trying to delete something that is not a reply.")

        #clean up the reference from the original activity
        activity = Activity()
        activity.get(key=self._dict['object']['inReplyTo']['id'])
        activity._dict['replies']['totalItems'] -= 1
        activity._dict['replies']['items'] = filter(lambda x: x["id"] != key, activity._dict['replies']['items'])

        self.save()
        activity.save()


class LikeActivity(ReplyActivity):
    def delete(self, key=None):
        self.get(key=key)
        if self._dict['verb'] != 'reply':
            raise SunspearValidationException("Trying to delete something that is not a reply.")

        #clean up the reference from the original activity
        activity = Activity()
        activity.get(key=self._dict['object']['inReplyTo']['id'])
        activity._dict['likes']['totalItems'] -= 1
        activity._dict['likes']['items'] = filter(lambda x: x["id"] != key)

        self.save()
        activity.save()

        return activity._riak_object


class Object(Model):
    _required_fields = ['objectType', 'id', 'published']
    _media_fields = ['image']


class MediaLink(Model):
    _required_fields = ['url']
