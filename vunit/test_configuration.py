# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014, Lars Asplund lars.anders.asplund@gmail.com

import logging
logger = logging.getLogger(__name__)


class TestConfiguration:
    def __init__(self):
        self._generics = {}
        self._configs = {}
        self._plis = {}

    def set_generic(self, name, value, scope=""):
        if scope not in self._generics:
            self._generics[scope] = {}
        self._generics[scope][name] = value

    def set_pli(self, value, scope=""):
        self._plis[scope] = value

    def add_config(self, tb_name, name, generics, post_check=None):
        if tb_name not in self._configs:
            self._configs[tb_name] = {}
        self._configs[tb_name][name] = (generics, post_check)

    def get_configurations(self, entity, architecture_name):
        tb_name = "%s.%s" % (entity.library_name, entity.name)

        configs = self._get_configurations_for_tb(entity)

        result = []
        for suffix, generics, pli, post_check in configs:
            if len(entity.architecture_names) > 1:
                config_name = dotjoin(tb_name, architecture_name, suffix)
            else:
                config_name = dotjoin(tb_name, suffix)

            result.append(Configuration(config_name, generics, post_check, pli))

        return result

    def _get_configurations_for_tb(self, entity):
        global_generics = self._get_generics_for_tb(entity.library_name, entity.name)
        global_generics = self._prune_generics(global_generics, entity.generic_names)
        pli = self._get_pli_for_tb(entity.library_name, entity.name)
        configs = []
        
        tb_name = "%s.%s" % (entity.library_name, entity.name)
        configs_for_tb_name = self._configs.get(tb_name, {})
        for config_name in sorted(configs_for_tb_name.keys()):
            cfg_generics, post_check = configs_for_tb_name[config_name]
            generics = global_generics.copy()
            generics.update(cfg_generics)
            generics = self._prune_generics(generics, entity.generic_names)
            configs.append((config_name, generics, pli, post_check))

        if len(configs) == 0:
            configs = [("", global_generics.copy(), pli, None)]
        return configs

    @staticmethod
    def _prune_generics(generics, generic_names):
        generics = generics.copy()
        for gname in list(generics.keys()):
            if gname not in generic_names:
                del generics[gname]
        return generics

    def _get_generics_for_tb(self, library_name, entity_name):
        generics = {}
        # Global
        generics.update(self._generics.get("", {}))
        # Library
        generics.update(self._generics.get(library_name, {}))
        # Enitity
        generics.update(self._generics.get(library_name + "." + entity_name, {}))
        return generics

    def _get_pli_for_tb(self, library_name, entity_name):
        # Global
        plis = self._plis.get("", [])
        # Library
        plis = self._plis.get(library_name, plis)
        # Enitity
        plis = self._plis.get(library_name + "." + entity_name, plis)
        return plis


class Configuration:
    def __init__(self,
                 name="",
                 generics=None,
                 post_check=None,
                 pli=None):
        self.name = name
        self.generics = generics if generics is not None else {}
        self.post_check = post_check
        self.pli = [] if pli is None else pli

    def __eq__(self, other):
        return (self.name == other.name and
                self.generics == other.generics and
                self.post_check == other.post_check and
                self.pli == other.pli)

    def __repr__(self):
        return("Configuration(%r, %r, %r, %r)"
               % (self.name, self.generics, self.post_check, self.pli))


def dotjoin(*args):
    """ string arguments joined by '.' unless empty string """
    return ".".join(arg for arg in args if not arg == "")
