from sunspear.aggregators.base import BaseAggregator
from sunspear.lib.dotdict import dotdictify

import copy


class PropertyAggregator(BaseAggregator):
    def __init__(self, properties=[], *args, **kwargs):
        self._properties = properties

    def _listify_attributes(self, group_by_attributes=[], activity={}):
        if not isinstance(activity, dotdictify):
            activity = dotdictify(activity)

        listified_dict = copy.copy(activity)

        nested_root_attributes = []
        #special handeling if we are grouping by a nested attribute
        #In this case, we listify all the other keys
        for attr in group_by_attributes:
            if '.' in attr:
                nested_val = activity.get(attr)
                if nested_val is not None:
                    nested_dict, deepest_attr = attr.rsplit('.', 1)
                    nested_root, rest = attr.split('.', 1)
                    #store a list of nested roots. We'll have to be careful not to listify these
                    nested_root_attributes.append(nested_root)
                    for nested_dict_key, nested_dict_value in activity.get(nested_dict).items():
                        if nested_dict_key != deepest_attr:
                            listified_dict['.'.join([nested_dict, nested_dict_key])] = [nested_dict_value]

        #now we listify all other non nested attributes
        for key, val in activity.items():
            if key not in group_by_attributes and key not in nested_root_attributes:
                listified_dict[key] = [val]

        return nested_root_attributes, listified_dict

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

    def _aggregate_activities(self, group_by_attributes=[], grouped_activities=[]):
        """
        Rolls up activities by group_by_attributes, collapsing all grouped activities into one activity object
        """
        grouped_activities_list = []
        for keys, group in grouped_activities:
            group_list = list(group)
            #special case. If we just grouped one activity, we don't need to aggregate
            if len(group_list) == 1:
                grouped_activities_list.append(group_list[0])
            else:
                #we have sevral activities that can be grouped together
                aggregated_activity = dotdictify({})
                aggregated_activity.update(group_list[0])

                nested_root_attributes, aggregated_activity = self._listify_attributes(group_by_attributes=group_by_attributes,\
                    activity=aggregated_activity)

                #aggregate the rest of the activities into lists
                for activity in group_list[1:]:
                    activity = dotdictify(activity)
                    for key in aggregated_activity.keys():
                        if key not in group_by_attributes and key not in nested_root_attributes:
                            aggregated_activity[key].append(activity.get(key))

                    #for nested attributes append all other attributes in a list
                    for attr in group_by_attributes:
                        if '.' in attr:
                            nested_val = activity.get(attr)
                            if nested_val is not None:
                                nested_dict, deepest_attr = attr.rsplit('.', 1)

                                for nested_dict_key, nested_dict_value in activity.get(nested_dict).items():
                                    if nested_dict_key != deepest_attr:
                                        aggregated_activity['.'.join([nested_dict, nested_dict_key])].append(nested_dict_value)

                #this might not be useful but meh, we'll see
                aggregated_activity.update({'grouped_by_values': keys})
                grouped_activities_list.append(aggregated_activity)
        return grouped_activities_list
