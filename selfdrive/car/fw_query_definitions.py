#!/usr/bin/env python3
import capnp
import copy
from dataclasses import dataclass, field
import struct
from typing import Callable, Dict, List, Optional, Set, Tuple

import panda.python.uds as uds

AddrType = Tuple[int, Optional[int]]
EcuAddrBusType = Tuple[int, Optional[int], int]
EcuAddrSubAddr = Tuple[int, int, Optional[int]]

LiveFwVersions = Dict[AddrType, Set[bytes]]
OfflineFwVersions = Dict[str, Dict[EcuAddrSubAddr, List[bytes]]]

STANDARD_VIN_ADDRS = [0x7e0, 0x7e2, 0x18da10f1, 0x18da0ef1]  # engine, VMCU, 29-bit engine, PGM-FI


def p16(val):
  return struct.pack("!H", val)


class StdQueries:
  # FW queries
  TESTER_PRESENT_REQUEST = bytes([uds.SERVICE_TYPE.TESTER_PRESENT, 0x0])
  TESTER_PRESENT_RESPONSE = bytes([uds.SERVICE_TYPE.TESTER_PRESENT + 0x40, 0x0])

  SHORT_TESTER_PRESENT_REQUEST = bytes([uds.SERVICE_TYPE.TESTER_PRESENT])
  SHORT_TESTER_PRESENT_RESPONSE = bytes([uds.SERVICE_TYPE.TESTER_PRESENT + 0x40])

  DEFAULT_DIAGNOSTIC_REQUEST = bytes([uds.SERVICE_TYPE.DIAGNOSTIC_SESSION_CONTROL,
                                      uds.SESSION_TYPE.DEFAULT])
  DEFAULT_DIAGNOSTIC_RESPONSE = bytes([uds.SERVICE_TYPE.DIAGNOSTIC_SESSION_CONTROL + 0x40,
                                      uds.SESSION_TYPE.DEFAULT, 0x0, 0x32, 0x1, 0xf4])

  EXTENDED_DIAGNOSTIC_REQUEST = bytes([uds.SERVICE_TYPE.DIAGNOSTIC_SESSION_CONTROL,
                                       uds.SESSION_TYPE.EXTENDED_DIAGNOSTIC])
  EXTENDED_DIAGNOSTIC_RESPONSE = bytes([uds.SERVICE_TYPE.DIAGNOSTIC_SESSION_CONTROL + 0x40,
                                        uds.SESSION_TYPE.EXTENDED_DIAGNOSTIC, 0x0, 0x32, 0x1, 0xf4])

  MANUFACTURER_SOFTWARE_VERSION_REQUEST = bytes([uds.SERVICE_TYPE.READ_DATA_BY_IDENTIFIER]) + \
    p16(uds.DATA_IDENTIFIER_TYPE.VEHICLE_MANUFACTURER_ECU_SOFTWARE_NUMBER)
  MANUFACTURER_SOFTWARE_VERSION_RESPONSE = bytes([uds.SERVICE_TYPE.READ_DATA_BY_IDENTIFIER + 0x40]) + \
    p16(uds.DATA_IDENTIFIER_TYPE.VEHICLE_MANUFACTURER_ECU_SOFTWARE_NUMBER)

  UDS_VERSION_REQUEST = bytes([uds.SERVICE_TYPE.READ_DATA_BY_IDENTIFIER]) + \
    p16(uds.DATA_IDENTIFIER_TYPE.APPLICATION_SOFTWARE_IDENTIFICATION)
  UDS_VERSION_RESPONSE = bytes([uds.SERVICE_TYPE.READ_DATA_BY_IDENTIFIER + 0x40]) + \
    p16(uds.DATA_IDENTIFIER_TYPE.APPLICATION_SOFTWARE_IDENTIFICATION)

  OBD_VERSION_REQUEST = b'\x09\x04'
  OBD_VERSION_RESPONSE = b'\x49\x04'

  # VIN queries
  OBD_VIN_REQUEST = b'\x09\x02'
  OBD_VIN_RESPONSE = b'\x49\x02\x01'

  UDS_VIN_REQUEST = bytes([uds.SERVICE_TYPE.READ_DATA_BY_IDENTIFIER]) + p16(uds.DATA_IDENTIFIER_TYPE.VIN)
  UDS_VIN_RESPONSE = bytes([uds.SERVICE_TYPE.READ_DATA_BY_IDENTIFIER + 0x40]) + p16(uds.DATA_IDENTIFIER_TYPE.VIN)

  GM_VIN_REQUEST = b'\x1a\x90'
  GM_VIN_RESPONSE = b'\x5a\x90'


@dataclass
class Request:
  request: List[bytes]
  response: List[bytes]
  whitelist_ecus: List[int] = field(default_factory=list)
  rx_offset: int = 0x8
  bus: int = 1
  # Whether this query should be run on the first auxiliary panda (CAN FD cars for example)
  auxiliary: bool = False
  # FW responses from these queries will not be used for fingerprinting
  logging: bool = False
  # boardd toggles OBD multiplexing on/off as needed
  obd_multiplexing: bool = True


@dataclass
class FwQueryConfig:
  requests: List[Request]
  # TODO: make this automatic and remove hardcoded lists, or do fingerprinting with ecus
  # Overrides and removes from essential ecus for specific models and ecus (exact matching)
  non_essential_ecus: Dict[capnp.lib.capnp._EnumModule, List[str]] = field(default_factory=dict)
  # Ecus added for data collection, not to be fingerprinted on
  extra_ecus: List[Tuple[capnp.lib.capnp._EnumModule, int, Optional[int]]] = field(default_factory=list)
  # Function a brand can implement to provide better fuzzy matching. Takes in FW versions,
  # returns set of candidates. Only will match if one candidate is returned
  match_fw_to_car_fuzzy: Optional[Callable[[LiveFwVersions, OfflineFwVersions], Set[str]]] = None

  def __post_init__(self):
    for i in range(len(self.requests)):
      if self.requests[i].auxiliary:
        new_request = copy.deepcopy(self.requests[i])
        new_request.bus += 4
        self.requests.append(new_request)

  def get_all_ecus(self, offline_fw_versions: OfflineFwVersions, include_ecu_type: bool = True,
                   include_extra_ecus: bool = True) -> set[EcuAddrSubAddr] | set[AddrType]:
    # Add ecus in database + extra ecus
    brand_ecus = {ecu for ecus in offline_fw_versions.values() for ecu in ecus}

    if include_extra_ecus:
      brand_ecus |= set(self.extra_ecus)

    if not include_ecu_type:
      return {(addr, subaddr) for _, addr, subaddr in brand_ecus}

    return brand_ecus
