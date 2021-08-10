from __future__ import absolute_import

from nose.tools import ok_, eq_, raises, set_trace

from sunspear.aggregators.property import PropertyAggregator
from sunspear.backends import RiakBackend
from sunspear.exceptions import SunspearValidationException, SunspearNotFoundException

from itertools import groupby


class TestPropertyAggregator(object):
    def setUp(self):
        self._aggregator = PropertyAggregator()

    def test__aggregate_activities(self):
        group_by_attributes = ['b', 'c.e']

        data_dict = [{'a': 1, 'b': 2, 'c': {'d': 3, 'e': 4}
        }, {'a': 3, 'b': 2,  'c': {'d': 5, 'e': 4}
        }, {'a': 4, 'b': 2, 'c': {'d': 6, 'e': 4}
        }, {'a': 5, 'b': 3, 'c': {'d': 6, 'e': 4}
        }]
        expected = [{'a': [1, 3, 4], 'c': {'e': 4, 'd': [3, 5, 6]}, 'b': 2, 'grouped_by_attributes': ['b', 'c.e'],
            'grouped_by_values': [2, 4]}, {'a': 5, 'c': {'e': 4, 'd': 6}, 'b': 3}]

        _raw_group_actvities = groupby(data_dict, self._aggregator._group_by_aggregator(group_by_attributes))
        actual = self._aggregator._aggregate_activities(group_by_attributes=group_by_attributes, grouped_activities=_raw_group_actvities)
        eq_(actual, expected)

    def test__listify_attributes(self):
        data_dict = {
            'a': 1,
            'b': 2,
            'c': {
                'd': 3,
                'e': 4
            }
        }
        group_by_attributes = ['a', 'a.c.f', 'c.e']
        expected = {
            'a': 1,
            'b': [2],
            'c': {
                'd': [3],
                'e': 4
            }
        }

        actual = self._aggregator._listify_attributes(group_by_attributes=group_by_attributes, activity=data_dict)
        eq_(actual, (['c'], expected,))

    def test_group_by_aggregator(self):
        data_dict = {
            'a': 1,
            'b': 2,
            'c': {
                'd': 3,
                'e': 4
            }
        }
        expected = [1, 2, 4]
        actual = self._aggregator._group_by_aggregator(group_by_attributes=['a', 'b', 'a.c.f', 'c.e'])(data_dict)
        eq_(expected, actual)
