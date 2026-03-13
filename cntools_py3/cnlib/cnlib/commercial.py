# -*- coding: utf-8 -*-

"""
Cognitive Networks commercial content ID conventions
"""

COMMERCIAL = 'C(^.~)c_Commercial_'  # our beloved winky face
__all__ = ['COMMERCIAL', 'is_commercial', 'is_cd_commercial']


def is_commercial(cid):
    """is the `cid` is a commercial?"""
    return cid.startswith(COMMERCIAL)


def is_cd_commercial(cid):
    """
    is the `cid` a commercial-detector commercial?
    Commercial detector commercials have CIDs like:

    C(^.~)c_Commercial_7536848_1417440944
    C(^.~)c_Commercial_7616668_1418103679
    C(^.~)c_Commercial_7585620_1417822252
    C(^.~)c_Commercial_7543091_1417494993
    C(^.~)c_Commercial_7551421_1417562891
    C(^.~)c_Commercial_7543032_1417494979
    C(^.~)c_Commercial_7585984_1417820094
    C(^.~)c_Commercial_7543791_1417480316
    """
    if not is_commercial(cid):
        return False

    parts = cid.split(COMMERCIAL, 1)[-1].split('_')
    if len(parts) != 2:
        return False

    try:
        return bool([int(part) for part in parts])  # happens to be True
    except ValueError:
        return False
