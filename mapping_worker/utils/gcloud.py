#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Author: Daniel E. Cook

Utility functions for running the task

"""
import arrow
import json
import pandas as pd
from io import StringIO
from gcloud import datastore, storage


def get_item(kind, name):
    """
        returns item by kind and name from google datastore
    """
    ds = datastore.Client(project='andersen-lab')
    result = ds.get(ds.key(kind, name))
    try:
        result_out = {'_exists': True}
        for k, v in result.items():
            if isinstance(v, str) and v.startswith("JSON:"):
                result_out[k] = json.loads(v[5:])
            elif v:
                result_out[k] = v

        return result_out
    except AttributeError:
        return None


def store_item(kind, name, **kwargs):
    ds = datastore.Client(project='andersen-lab')
    exclude = kwargs.pop('exclude_from_indexes')
    print(kwargs)
    if exclude:
        m = datastore.Entity(key=ds.key(kind, name), exclude_from_indexes=exclude)
    else:
        m = datastore.Entity(key=ds.key(kind, name))
    for key, value in kwargs.items():
        if isinstance(value, dict):
            m[key] = 'JSON:' + json.dumps(value)
        else:
            m[key] = value
    ds.put(m)


class datastore_model(object):
    """
        Base datastore model

        Google datastore is used to store dynamic information
        such as users and reports.

        Note that the 'kind' must be defined within sub
    """

    def __init__(self, name):
        self.name = name
        self.exclude_from_indexes = None
        item = get_item(self.kind, name)
        if item:
            self._exists = True
            self.__dict__.update(item)
        else:
            self._exists = False
        print(self._exists)

    def save(self):
        self._exists = True
        item_data = {k: v for k, v in self.__dict__.items() if k not in ['kind', 'name'] and not k.startswith("_")}
        store_item(self.kind, self.name, **item_data)

    def __repr__(self):
        return f"<{self.kind}:{self.name}>"


class report_m(datastore_model):
    """
        The report model - for creating and retreiving
        information on reports
    """
    kind = 'report'
    def __init__(self, *args, **kwargs):
        super(report_m, self).__init__(*args, **kwargs)
        self.exclude_from_indexes = ('trait_data',)
        # Read trait data in upon initialization.
        if hasattr(self, 'trait_data'):
            self._trait_df = pd.read_csv(StringIO(self.trait_data), sep='\t')

    def trait_strain_count(self, trait_name):
        """
            Return number of strains submitted for a trait.
        """
        return self._trait_df[trait_name].dropna(how='any').count()

    def humanize(self):
        return arrow.get(self.created_on).humanize()


class trait_m(datastore_model):
    """
        Class for storing data on tasks
        associated with a report.
    """
    kind = 'trait'
