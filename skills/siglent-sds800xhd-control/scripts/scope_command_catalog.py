#!/usr/bin/env python3
"""Documented SDS800X HD SCPI catalog for the configuration engine.

Provenance
----------
Every entry is transcribed from ``SDS800XHD_Series_ProgrammingGuide_CN11G``
(printed pages 68-410; PDF pages 96-438). Nothing here is hardware-verified on
its own: the catalog records what the manual documents -- command spelling,
argument domain, risk class, and the printed page that states it. The scope's
own readback response is the only authority for a value that was actually set.

The table is generated, not hand-edited. Regenerate it from the manual with the
parser kept outside the repository; hand edits would silently drift from the
documented domain.

Entry layout
------------
``command`` is the manual heading with its index placeholder preserved
(``<n>``, ``<m>``, ``<x>``, ``<r>``). ``kind`` describes the argument domain:

``enum``         value must be one of ``choices`` (case-insensitive prefix match)
``enum_prefix``  value starts with one of ``choices`` and may carry a trailing
                 ``[,<value>]`` or ``,<index>``/``,<path>`` argument
``int``/``float``/``number``  numeric, optionally bounded by ``minimum``/``maximum``
``string``       quoted text or a storage path
``compound``     several comma-separated arguments; only the shape is known
``action``       no argument
``any``          the manual gives no domain (or it is model-dependent)

``risk`` is the class the engine requires explicit permission for:

``display``             analysis/display configuration only
``acquisition_context`` trigger or acquisition configuration
``file_write``          writes a file to internal/network/USB storage
``destructive``         erases user storage or restores factory defaults

``has_query`` is true when the manual documents a readback query for the
command. Commands without one cannot be verified by readback and must not be
presented as confirmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CommandSpec:
    command: str
    kind: str
    choices: tuple[str, ...]
    minimum: float | None
    maximum: float | None
    args: tuple[str, ...]
    indices: dict[str, tuple[str, ...] | None] = field(default_factory=dict)
    risk: str = "display"
    page: int = 0
    has_query: bool = True

    @property
    def query(self) -> str | None:
        return self.command + "?" if self.has_query else None


# command: (kind, choices, minimum, maximum, args, indices, risk, page, has_query)
RAW = {
    ':DECode': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 68, True),
    ':DECode:BUS<n>': ('enum', ("ON","OFF"), None, None, ('state',), {"n":("1","2")}, 'display', 70, True),
    ':DECode:BUS<n>:CAN': ('action', (), None, None, (), {"n":None}, 'display', 91, False),
    ':DECode:BUS<n>:CAN:BAUD': ('enum_prefix', ("5kbps","10kbps","20kbps","50kbps","100kbps","125kbps","250kbps","500kbps","800kbps","1Mbps","CUSTom"), None, None, ('baud',), {"n":("1","2")}, 'display', 91, True),
    ':DECode:BUS<n>:CAN:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 91, True),
    ':DECode:BUS<n>:CAN:THReshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 92, True),
    ':DECode:BUS<n>:CANFd': ('action', (), None, None, (), {"n":None}, 'display', 97, False),
    ':DECode:BUS<n>:CANFd:BAUDData': ('enum_prefix', ("500kbps","1Mbps","2Mbps","5Mbps","8Mbps","10Mbps","CUSTom"), None, None, ('baud',), {"n":("1","2")}, 'display', 97, True),
    ':DECode:BUS<n>:CANFd:BAUDNominal': ('enum_prefix', ("10kbps","25kbps","50kbps","100kbps","250kbps","1Mbps","CUSTom"), None, None, ('baud',), {"n":("1","2")}, 'display', 97, True),
    ':DECode:BUS<n>:CANFd:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 98, True),
    ':DECode:BUS<n>:CANFd:THReshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 98, True),
    ':DECode:BUS<n>:COPY': ('enum', ("FROMtrigger","TOTRigger"), None, None, ('operation',), {"n":("1","2")}, 'display', 71, False),
    ':DECode:BUS<n>:FLEXray': ('action', (), None, None, (), {"n":None}, 'display', 95, False),
    ':DECode:BUS<n>:FLEXray:BAUD': ('enum_prefix', ("2500kbps","5Mbps","10Mbps","CUSTom"), None, None, ('baud',), {"n":("1","2")}, 'display', 95, True),
    ':DECode:BUS<n>:FLEXray:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 95, True),
    ':DECode:BUS<n>:FLEXray:THReshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 96, True),
    ':DECode:BUS<n>:FORMat': ('enum', ("BINary","DECimal","HEX","ASCii"), None, None, ('formal',), {"n":("1","2")}, 'display', 71, True),
    ':DECode:BUS<n>:IIC': ('action', (), None, None, (), {"n":None}, 'display', 73, False),
    ':DECode:BUS<n>:IIC:RWBit': ('enum', ("ON","OFF"), None, None, ('state',), {"n":("1","2")}, 'display', 73, True),
    ':DECode:BUS<n>:IIC:SCLSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 73, True),
    ':DECode:BUS<n>:IIC:SCLThreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 74, True),
    ':DECode:BUS<n>:IIC:SDASource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 74, True),
    ':DECode:BUS<n>:IIC:SDAThreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 75, True),
    ':DECode:BUS<n>:IIS': ('action', (), None, None, (), {"n":None}, 'display', 100, False),
    ':DECode:BUS<n>:IIS:ANNotate': ('enum', ("ALL","LEFT","RIGHt"), None, None, ('type',), {"n":("1","2")}, 'display', 100, True),
    ':DECode:BUS<n>:IIS:AVARiant': ('enum', ("I2S","LJ","RJ"), None, None, ('type',), {"n":("1","2")}, 'display', 100, True),
    ':DECode:BUS<n>:IIS:BCLKSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 101, True),
    ':DECode:BUS<n>:IIS:BCLKThreshold': ('any', (), None, None, ('value',), {"n":("1","2")}, 'display', 101, True),
    ':DECode:BUS<n>:IIS:BITorder': ('enum', ("LSB","MSB"), None, None, ('order',), {"n":("1","2")}, 'display', 102, True),
    ':DECode:BUS<n>:IIS:DLENgth': ('int', (), 1.0, 32.0, ('value',), {"n":("1","2")}, 'display', 102, True),
    ':DECode:BUS<n>:IIS:DSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 103, True),
    ':DECode:BUS<n>:IIS:DTHReshold': ('any', (), None, None, ('value',), {"n":("1","2")}, 'display', 103, True),
    ':DECode:BUS<n>:IIS:LATChedge': ('enum', ("RISing","FALLing"), None, None, ('slope',), {"n":("1","2")}, 'display', 104, True),
    ':DECode:BUS<n>:IIS:LCH': ('enum', ("LOW","HIGH"), None, None, ('left',), {"n":("1","2")}, 'display', 104, True),
    ':DECode:BUS<n>:IIS:SBIT': ('int', (), 1.0, 31.0, ('value',), {"n":("1","2")}, 'display', 105, True),
    ':DECode:BUS<n>:IIS:WSSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 105, True),
    ':DECode:BUS<n>:IIS:WSTHreshold': ('any', (), None, None, ('value',), {"n":("1","2")}, 'display', 106, True),
    ':DECode:BUS<n>:LIN': ('action', (), None, None, (), {"n":None}, 'display', 93, False),
    ':DECode:BUS<n>:LIN:BAUD': ('enum_prefix', ("600bps","1200bps","2400bps","4800bps","9600bps","19200bps","CUSTom"), None, None, ('baud',), {"n":("1","2")}, 'display', 93, True),
    ':DECode:BUS<n>:LIN:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 93, True),
    ':DECode:BUS<n>:LIN:THReshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 94, True),
    ':DECode:BUS<n>:M1553': ('action', (), None, None, (), {"n":None}, 'display', 107, False),
    ':DECode:BUS<n>:M1553:LTHReshold': ('any', (), None, None, ('value',), {"n":("1","2")}, 'display', 107, True),
    ':DECode:BUS<n>:M1553:SOURce': ('enum', ("C<n>",), None, None, ('source',), {"n":("1","2")}, 'display', 107, True),
    ':DECode:BUS<n>:M1553:UTHReshold': ('any', (), None, None, ('value',), {"n":("1","2")}, 'display', 108, True),
    ':DECode:BUS<n>:MANChester': ('action', (), None, None, (), {"n":None}, 'display', 114, False),
    ':DECode:BUS<n>:MANChester:BAUD': ('any', (), None, None, ('baud',), {"n":("1","2")}, 'display', 115, True),
    ':DECode:BUS<n>:MANChester:BITorder': ('enum', ("LSB","MSB"), None, None, ('order',), {"n":("1","2")}, 'display', 120, True),
    ':DECode:BUS<n>:MANChester:DISPlay': ('enum', ("WORD","BIT"), None, None, ('format',), {"n":("1","2")}, 'display', 119, True),
    ':DECode:BUS<n>:MANChester:DSIZe': ('int', (), 1.0, 255.0, ('value',), {"n":("1","2")}, 'display', 119, True),
    ':DECode:BUS<n>:MANChester:HSIZe': ('int', (), 0.0, 32.0, ('value',), {"n":("1","2")}, 'display', 117, True),
    ':DECode:BUS<n>:MANChester:IBITs': ('int', (), 2.0, 32.0, ('value',), {"n":("1","2")}, 'display', 116, True),
    ':DECode:BUS<n>:MANChester:IDLE': ('enum', ("LOW","HIGH"), None, None, ('idle',), {"n":("1","2")}, 'display', 116, True),
    ':DECode:BUS<n>:MANChester:POLarity': ('enum', ("RISing","FALLing"), None, None, ('polar',), {"n":("1","2")}, 'display', 115, True),
    ':DECode:BUS<n>:MANChester:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 114, True),
    ':DECode:BUS<n>:MANChester:SSIZe': ('int', (), 0.0, 32.0, ('value',), {"n":("1","2")}, 'display', 117, True),
    ':DECode:BUS<n>:MANChester:STARt': ('int', (), 1.0, 32.0, ('value',), {"n":("1","2")}, 'display', 117, True),
    ':DECode:BUS<n>:MANChester:THReshold': ('any', (), None, None, ('value',), {"n":("1","2")}, 'display', 114, True),
    ':DECode:BUS<n>:MANChester:TSIZe': ('int', (), 0.0, 32.0, ('value',), {"n":("1","2")}, 'display', 118, True),
    ':DECode:BUS<n>:MANChester:WSIZe': ('int', (), 2.0, 8.0, ('value',), {"n":("1","2")}, 'display', 118, True),
    ':DECode:BUS<n>:PROTocol': ('enum', ("IIC","SPI","UART","CAN","LIN","FLEXray","CANFd","IIS","M1553","SENT","MANchester","ARINC429","USB20"), None, None, ('protocol',), {"n":("1","2")}, 'display', 71, True),
    ':DECode:BUS<n>:RESult': ('action', (), None, None, (), {"n":("1","2")}, 'display', 72, True),
    ':DECode:BUS<n>:SENT': ('action', (), None, None, (), {"n":None}, 'display', 109, False),
    ':DECode:BUS<n>:SENT:CLOCk': ('float', (), 5e-07, 0.0003, ('value',), {"n":("1","2")}, 'display', 110, True),
    ':DECode:BUS<n>:SENT:CRC': ('enum', ("OFF","ON"), None, None, ('state',), {"n":("1","2")}, 'display', 112, True),
    ':DECode:BUS<n>:SENT:FORMat': ('enum', ("NIBBles","FSIGnal","SSERial","ESERial"), None, None, ('format',), {"n":("1","2")}, 'display', 110, True),
    ':DECode:BUS<n>:SENT:IDLE': ('enum', ("LOW","HIGH"), None, None, ('idle',), {"n":("1","2")}, 'display', 111, True),
    ':DECode:BUS<n>:SENT:LENGth': ('int', (), 3.0, 8.0, ('value',), {"n":("1","2")}, 'display', 112, True),
    ':DECode:BUS<n>:SENT:PPULse': ('enum', ("OFF","ON"), None, None, ('state',), {"n":None}, 'display', 113, True),
    ':DECode:BUS<n>:SENT:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 109, True),
    ':DECode:BUS<n>:SENT:THReshold': ('any', (), None, None, ('value',), {"n":("1","2")}, 'display', 109, True),
    ':DECode:BUS<n>:SENT:TOLerance': ('int', (), 1.0, 25.0, ('value',), {"n":("1","2")}, 'display', 111, True),
    ':DECode:BUS<n>:SPI': ('action', (), None, None, (), {"n":None}, 'display', 76, False),
    ':DECode:BUS<n>:SPI:BITorder': ('enum', ("LSB","MSB"), None, None, ('order',), {"n":("1","2")}, 'display', 76, True),
    ':DECode:BUS<n>:SPI:CLKSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 76, True),
    ':DECode:BUS<n>:SPI:CLKThreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 77, True),
    ':DECode:BUS<n>:SPI:CSSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 77, True),
    ':DECode:BUS<n>:SPI:CSTYpe': ('enum_prefix', ("NCS","CS","TIMeout"), None, None, ('type',), {"n":("1","2")}, 'display', 79, True),
    ':DECode:BUS<n>:SPI:CSThreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 78, True),
    ':DECode:BUS<n>:SPI:DLENgth': ('int', (), 4.0, 32.0, ('value',), {"n":("1","2")}, 'display', 79, True),
    ':DECode:BUS<n>:SPI:LATChedge': ('enum', ("RISing","FALLing"), None, None, ('slope',), {"n":("1","2")}, 'display', 80, True),
    ':DECode:BUS<n>:SPI:MISOSource': ('enum', ("C<n>","D<d>","DIS"), None, None, ('source',), {"n":("1","2")}, 'display', 80, True),
    ':DECode:BUS<n>:SPI:MISOThreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 81, True),
    ':DECode:BUS<n>:SPI:MOSISource': ('enum', ("C<n>","D<d>","DIS"), None, None, ('source',), {"n":("1","2")}, 'display', 81, True),
    ':DECode:BUS<n>:SPI:MOSIThreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 82, True),
    ':DECode:BUS<n>:SPI:NCSSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {"n":("1","2")}, 'display', 83, True),
    ':DECode:BUS<n>:SPI:NCSThreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 83, True),
    ':DECode:BUS<n>:UART': ('action', (), None, None, (), {"n":None}, 'display', 85, False),
    ':DECode:BUS<n>:UART:BAUD': ('enum_prefix', ("600bps","1200bps","2400bps","4800bps","9600bps","19200bps","38400bps","57600bps","115200bps","CUSTom"), None, None, ('baud',), {"n":("1","2")}, 'display', 85, True),
    ':DECode:BUS<n>:UART:BITorder': ('enum', ("LSB","MSB"), None, None, ('order',), {"n":("1","2")}, 'display', 85, True),
    ':DECode:BUS<n>:UART:DLENgth': ('int', (), 5.0, 8.0, ('value',), {"n":("1","2")}, 'display', 86, True),
    ':DECode:BUS<n>:UART:IDLE': ('enum', ("LOW","HIGH"), None, None, ('idle',), {"n":("1","2")}, 'display', 86, True),
    ':DECode:BUS<n>:UART:PARity': ('enum', ("NONE","ODD","EVEN","MARK","SPACe"), None, None, ('parity',), {"n":("1","2")}, 'display', 87, True),
    ':DECode:BUS<n>:UART:RXSource': ('enum', ("C<n>","D<d>","DIS"), None, None, ('source',), {"n":("1","2")}, 'display', 87, True),
    ':DECode:BUS<n>:UART:RXTHreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 88, True),
    ':DECode:BUS<n>:UART:STOP': ('enum', ("1","1.5","2"), None, None, ('bit',), {"n":("1","2")}, 'display', 88, True),
    ':DECode:BUS<n>:UART:TXSource': ('enum', ("C<n>","D<d>","DIS"), None, None, ('source',), {"n":("1","2")}, 'display', 89, True),
    ':DECode:BUS<n>:UART:TXTHreshold': ('float', (), None, None, ('value',), {"n":("1","2")}, 'display', 89, True),
    ':DECode:LIST': ('enum', ("OFF","D1","D2"), None, None, ('state',), {}, 'display', 68, True),
    ':DECode:LIST:LINE': ('int', (), 1.0, 7.0, ('value',), {}, 'display', 69, True),
    ':DECode:LIST:SCRoll': ('int', (), None, None, ('value',), {}, 'display', 69, True),
    ':DECode:LIST<n>:RESult': ('action', (), None, None, (), {"n":("1","2")}, 'display', 70, True),
    ':FUNCtion:FFTDisplay': ('enum', ("SPLit","FULL","EXCLusive"), None, None, ('mode',), {}, 'display', 138, True),
    ':FUNCtion:GVALue': ('compound', (), None, None, ('valueA', 'valueB'), {}, 'display', 138, True),
    ':FUNCtion<x>': ('enum', ("ON","OFF"), None, None, ('state',), {"x":None}, 'display', 139, True),
    ':FUNCtion<x>:AVERage:NUM': ('any', (), None, None, ('num',), {"x":None}, 'display', 139, True),
    ':FUNCtion<x>:DIFF:DX': ('int', (), None, None, ('dx',), {"x":None}, 'display', 140, True),
    ':FUNCtion<x>:ERES:BITS': ('enum', ("0.5","1.0","1.5","2.0","2.5","3.0"), None, None, ('bits',), {"x":None}, 'display', 140, True),
    ':FUNCtion<x>:FFT:AUToset': ('enum', ("SPAN","PEAK","NORMal"), None, None, ('mode',), {"x":None}, 'display', 141, False),
    ':FUNCtion<x>:FFT:HCENter': ('float', (), None, None, ('center',), {"x":None}, 'display', 141, True),
    ':FUNCtion<x>:FFT:HSCale': ('action', (), None, None, (), {"x":None}, 'display', 142, True),
    ':FUNCtion<x>:FFT:LOAD': ('int', (), 1.0, 1000000.0, ('load',), {"x":None}, 'display', 142, True),
    ':FUNCtion<x>:FFT:MODE': ('enum_prefix', ("NORMal","MAXHold","AVERage"), None, None, ('mode',), {"x":None}, 'display', 143, True),
    ':FUNCtion<x>:FFT:POINts': ('any', (), None, None, ('point',), {"x":None}, 'display', 144, True),
    ':FUNCtion<x>:FFT:RESET': ('action', (), None, None, (), {"x":None}, 'display', 144, False),
    ':FUNCtion<x>:FFT:RLEVel': ('float', (), -40.0, 200.0, ('level',), {"x":None}, 'display', 145, True),
    ':FUNCtion<x>:FFT:SCALe': ('float', (), 0.1, 20.0, ('scale',), {"x":None}, 'display', 146, True),
    ':FUNCtion<x>:FFT:SEARch': ('enum', ("OFF","PEAK","MARKer"), None, None, ('type',), {"x":None}, 'display', 146, True),
    ':FUNCtion<x>:FFT:SEARch:EXCursion': ('float', (), 0.0, 160.0, ('value',), {"x":None}, 'display', 147, True),
    ':FUNCtion<x>:FFT:SEARch:MARKer<n>': ('enum', ("NPeak","NAMPlitude"), None, None, ('freq',), {"n":None,"x":None}, 'display', 147, False),
    ':FUNCtion<x>:FFT:SEARch:MARKer<n>:SHOW': ('enum', ("ON","OFF"), None, None, ('state',), {"n":None,"x":None}, 'display', 147, False),
    ':FUNCtion<x>:FFT:SEARch:MON': ('enum', ("PEAK","HARMonics"), None, None, ('type',), {"x":None}, 'display', 148, False),
    ':FUNCtion<x>:FFT:SEARch:PORDer': ('enum', ("AMPLitude","FREQuency"), None, None, ('type',), {"x":None}, 'display', 148, True),
    ':FUNCtion<x>:FFT:SEARch:RESult': ('action', (), None, None, (), {"x":None}, 'display', 149, True),
    ':FUNCtion<x>:FFT:SEARch:TABLe': ('enum', ("ON","OFF"), None, None, ('state',), {"x":None}, 'display', 149, True),
    ':FUNCtion<x>:FFT:SEARch:TABLe:DELTa': ('enum', ("ON","OFF"), None, None, ('state',), {"x":None}, 'display', 150, True),
    ':FUNCtion<x>:FFT:SEARch:TABLe:FREQuency': ('enum', ("ON","OFF"), None, None, ('state',), {"x":None}, 'display', 150, True),
    ':FUNCtion<x>:FFT:SEARch:THReshold': ('float', (), -160.0, 80.0, ('value',), {"x":None}, 'display', 151, True),
    ':FUNCtion<x>:FFT:SPAN': ('float', (), None, None, ('span',), {"x":None}, 'display', 142, True),
    ':FUNCtion<x>:FFT:UNIT': ('enum', ("DBVrms","Vrms","DBm"), None, None, ('unit',), {"x":None}, 'display', 151, True),
    ':FUNCtion<x>:FFT:WINDow': ('enum', ("RECTangle","BLACkman","HANNing","HAMMing","FLATtop"), None, None, ('window',), {"x":None}, 'display', 152, True),
    ':FUNCtion<x>:FILTer:HFRequency': ('float', (), None, None, ('value',), {"x":None}, 'display', 153, True),
    ':FUNCtion<x>:FILTer:LFRequency': ('float', (), None, None, ('value',), {"x":None}, 'display', 153, True),
    ':FUNCtion<x>:FILTer:TYPe': ('enum', ("LPASs","HPASs","BPASs","BREJect"), None, None, ('type',), {"x":None}, 'display', 152, True),
    ':FUNCtion<x>:INTErpolate:COEF': ('enum', ("2","5","10","20"), None, None, ('coef',), {"x":None}, 'display', 155, True),
    ':FUNCtion<x>:INTegrate:GATE': ('enum', ("ON","OFF"), None, None, ('state',), {"x":None}, 'display', 154, True),
    ':FUNCtion<x>:INTegrate:OFFSet': ('float', (), None, None, ('offset',), {"x":None}, 'display', 155, True),
    ':FUNCtion<x>:INVert': ('enum', ("ON","OFF"), None, None, ('state',), {"x":None}, 'display', 155, True),
    ':FUNCtion<x>:LABel': ('enum', ("ON","OFF"), None, None, ('state',), {"x":None}, 'display', 156, True),
    ':FUNCtion<x>:LABel:TEXT': ('string', (), None, None, ('qstring',), {"x":None}, 'display', 156, True),
    ':FUNCtion<x>:MAXHold:Sweeps': ('int', (), 0.0, 2147483646.0, ('value',), {"x":None}, 'display', 157, True),
    ':FUNCtion<x>:MINHold:Sweeps': ('int', (), 1.0, 2147483646.0, ('value',), {"x":None}, 'display', 157, True),
    ':FUNCtion<x>:OPERation': ('enum', ("ADD","SUBTract","MULTiply","DIVision","INTegrate","DIFF","FFT","SQRT","ERES","AVERage","ABSolute","SIGN","IDENtity","NEGation","EXP","TEN","LN","LOG","INTErpolate","MAXHold","MINHold","FILTer"), None, None, ('operation',), {"x":None}, 'display', 158, True),
    ':FUNCtion<x>:POSition': ('float', (), -100000.0, 100000.0, ('offset',), {"x":None}, 'display', 158, True),
    ':FUNCtion<x>:SCALe': ('float', (), 0.0005, 10000.0, ('scale',), {"x":None}, 'display', 159, True),
    ':FUNCtion<x>:SOURce1': ('enum', ('C<n>','Z<n>','F<x>','M<m>'), None, None, ('source',), {'x':None}, 'display', 159, True),
    ':FUNCtion<x>:SOURce2': ('enum', ('C<n>','Z<n>','F<x>','M<m>'), None, None, ('source',), {'x':None}, 'display', 160, True),
    ':HISTORy': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 161, True),
    ':HISTORy:FRAMe': ('int', (), None, None, ('value',), {}, 'display', 161, True),
    ':HISTORy:INTERval': ('float', (), 1e-06, 1.0, ('value',), {}, 'display', 162, True),
    ':HISTORy:LIST': ('enum_prefix', ("OFF","ON"), None, None, ('state',), {}, 'display', 162, True),
    ':HISTORy:PLAY': ('enum', ("BACKWards","PAUSe","FORWards"), None, None, ('state',), {}, 'display', 163, True),
    ':HISTORy:TIME': ('action', (), None, None, (), {}, 'display', 163, True),
    ':MEMory<m>:HORizontal:POSition': ('float', (), None, None, ('val',), {"m":None}, 'display', 186, True),
    ':MEMory<m>:HORizontal:SCALe': ('float', (), None, None, ('value',), {"m":None}, 'display', 186, True),
    ':MEMory<m>:HORizontal:SYNC': ('enum', ("ON","OFF"), None, None, ('state',), {"m":None}, 'display', 187, True),
    ':MEMory<m>:IMPort': ('any', (), None, None, ('source',), {"m":None}, 'display', 187, False),
    ':MEMory<m>:LABel': ('enum', ("ON","OFF"), None, None, ('state',), {"m":None}, 'display', 187, True),
    ':MEMory<m>:LABel:TEXT': ('string', (), None, None, ('qstring',), {"m":None}, 'display', 188, True),
    ':MEMory<m>:SWITch': ('enum', ("ON","OFF"), None, None, ('state',), {"m":None}, 'display', 188, True),
    ':MEMory<m>:VERTical:POSition': ('float', (), None, None, ('offset',), {"m":None}, 'display', 189, True),
    ':MEMory<m>:VERTical:SCALe': ('float', (), None, None, ('scale',), {"m":None}, 'display', 189, True),
    ':MTESt': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 190, True),
    ':MTESt:COUNt': ('action', (), None, None, (), {}, 'display', 190, True),
    ':MTESt:FUNCtion:BUZZer': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 190, True),
    ':MTESt:FUNCtion:COF': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 191, True),
    ':MTESt:FUNCtion:FTH': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 191, True),
    ':MTESt:FUNCtion:SOF': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 192, True),
    ':MTESt:IDISplay': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 192, True),
    ':MTESt:MASK:CREate': ('compound', (), None, None, ('XMARgin', 'YMARgin'), {}, 'display', 193, False),
    ':MTESt:MASK:LOAD': ('enum_prefix', ("INTernal","EXTernal"), None, None, ('location',), {}, 'display', 193, False),
    ':MTESt:OPERate': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 194, True),
    ':MTESt:RESet': ('action', (), None, None, (), {}, 'destructive', 194, False),
    ':MTESt:SOURce': ('enum', ('C<n>','Z<n>'), None, None, ('source',), {}, 'display', 194, True),
    ':MTESt:TYPE': ('enum', ("ALL_IN","ALL_OUT","ANY_IN","ANY_OUT"), None, None, ('type',), {}, 'display', 195, True),
    ':RECall:FDEFault': ('action', (), None, None, (), {}, 'destructive', 196, False),
    ':RECall:REFerence': ('compound', (), None, None, ('location', 'path'), {}, 'file_write', 196, False),
    ':RECall:SERase': ('action', (), None, None, (), {}, 'destructive', 197, False),
    ':RECall:SETup': ('enum_prefix', ("INTernal","EXTernal"), None, None, ('state',), {}, 'file_write', 197, False),
    ':REF<r>:DATA': ('enum_prefix', ("LOAD","UNLoad","SAVE"), None, None, ('operation',), {"r":("A","B","C","D")}, 'display', 199, False),
    ':REF<r>:DATA:POSition': ('float', (), None, None, ('value',), {"r":("A","B","C","D")}, 'display', 200, True),
    ':REF<r>:DATA:SCALe': ('float', (), None, None, ('value',), {"r":("A","B","C","D")}, 'display', 199, True),
    ':REF<r>:DATA:SOURce': ('action', (), None, None, (), {"r":("A","B","C","D")}, 'display', 199, True),
    ':REF<r>:LABel': ('enum', ("ON","OFF"), None, None, ('state',), {"r":("A","B","C","D")}, 'display', 198, True),
    ':REF<r>:LABel:TEXT': ('string', (), None, None, ('qstring',), {"r":("A","B","C","D")}, 'display', 198, True),
    ':SAVE:BINary': ('compound', (), None, None, ('path', 'source'), {}, 'file_write', 201, False),
    ':SAVE:CSV': ('compound', (), None, None, ('path', 'source', 'state'), {}, 'file_write', 202, False),
    ':SAVE:DEFault': ('enum', ("CUSTom","FACTory"), None, None, ('set',), {}, 'destructive', 203, False),
    ':SAVE:IMAGe': ('compound', (), None, None, ('path', 'type', 'invert', 'menu'), {}, 'file_write', 203, False),
    ':SAVE:MATLab': ('compound', (), None, None, ('path', 'source'), {}, 'file_write', 204, False),
    ':SAVE:REFerence': ('compound', (), None, None, ('path', 'source'), {}, 'file_write', 205, False),
    ':SAVE:SETup': ('enum_prefix', ("INTernal","EXTernal"), None, None, ('setup_num',), {}, 'file_write', 205, False),
    ':SEARch': ('enum', ("ON","OFF"), None, None, ('state',), {}, 'display', 207, True),
    ':SEARch:COPY': ('enum', ("FROMtrigger","TOTRigger","CANCel"), None, None, ('operation',), {}, 'display', 208, False),
    ':SEARch:COUNT': ('action', (), None, None, (), {}, 'display', 208, True),
    ':SEARch:EDGE': ('action', (), None, None, (), {}, 'display', 209, False),
    ':SEARch:EDGE:LEVel': ('float', (), None, None, ('level_value',), {}, 'display', 210, True),
    ':SEARch:EDGE:SLOPe': ('enum', ("RISing","FALLing","ALTernate"), None, None, ('slope_type',), {}, 'display', 209, True),
    ':SEARch:EDGE:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'display', 209, True),
    ':SEARch:EVENt': ('action', (), None, None, (), {}, 'display', 208, True),
    ':SEARch:INTerval': ('action', (), None, None, (), {}, 'display', 220, False),
    ':SEARch:INTerval:LEVel': ('float', (), None, None, ('level_value',), {}, 'display', 221, True),
    ':SEARch:INTerval:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'display', 221, True),
    ':SEARch:INTerval:SLOPe': ('enum', ("RISing","FALLing"), None, None, ('slope_type',), {}, 'display', 220, True),
    ':SEARch:INTerval:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'display', 220, True),
    ':SEARch:INTerval:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 223, True),
    ':SEARch:INTerval:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 222, True),
    ':SEARch:MODE': ('enum', ("EDGE","SLOPe","PULSE","INTerval","RUNT"), None, None, ('mode',), {}, 'display', 207, True),
    ':SEARch:PULSe': ('action', (), None, None, (), {}, 'display', 216, True),
    ':SEARch:PULSe:LEVel': ('float', (), None, None, ('level_value',), {}, 'display', 217, True),
    ':SEARch:PULSe:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'display', 217, True),
    ':SEARch:PULSe:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 219, True),
    ':SEARch:PULSe:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 218, True),
    ':SEARch:PULse:POLarity': ('enum', ("POSitive","NEGative"), None, None, ('polarity',), {}, 'display', 216, True),
    ':SEARch:PULse:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'display', 216, True),
    ':SEARch:RUNT': ('action', (), None, None, (), {}, 'display', 224, False),
    ':SEARch:RUNT:HLEVel': ('float', (), None, None, ('high_level_value',), {}, 'display', 224, True),
    ':SEARch:RUNT:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'display', 226, True),
    ':SEARch:RUNT:LLEVel': ('float', (), None, None, ('low_level_value',), {}, 'display', 225, True),
    ':SEARch:RUNT:POLarity': ('enum', ("POSitive","NEGative"), None, None, ('polarity',), {}, 'display', 224, True),
    ':SEARch:RUNT:SOURce': ('enum', ("C<n>",), None, None, ('source',), {}, 'display', 224, True),
    ':SEARch:RUNT:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 227, True),
    ':SEARch:RUNT:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 227, True),
    ':SEARch:SLOPe': ('action', (), None, None, (), {}, 'display', 211, False),
    ':SEARch:SLOPe:HLEVel': ('float', (), None, None, ('high_level_value',), {}, 'display', 211, True),
    ':SEARch:SLOPe:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'display', 213, True),
    ':SEARch:SLOPe:LLEVel': ('float', (), None, None, ('low_level_value',), {}, 'display', 212, True),
    ':SEARch:SLOPe:SLOPe': ('enum', ("RISing","FALLing"), None, None, ('slope_type',), {}, 'display', 211, True),
    ':SEARch:SLOPe:SOURce': ('any', (), None, None, ('source',), {}, 'display', 211, True),
    ':SEARch:SLOPe:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 214, True),
    ':SEARch:SLOPe:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'display', 214, True),
    ':TRIGger:CAN': ('action', (), None, None, (), {}, 'acquisition_context', 352, False),
    ':TRIGger:CAN:BAUD': ('enum_prefix', ("5kbps","10kbps","20kbps","50kbps","100kbps","125kbps","250kbps","500kbps","800kbps","1Mbps","CUSTom"), None, None, ('baud',), {}, 'acquisition_context', 352, True),
    ':TRIGger:CAN:CONDition': ('enum', ("STARt","REMote","ID","ID_AND_DATA","ERRor"), None, None, ('condition',), {}, 'acquisition_context', 352, True),
    ':TRIGger:CAN:DAT2': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 353, True),
    ':TRIGger:CAN:DATA': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 353, True),
    ':TRIGger:CAN:ID': ('int', (), 0.0, 536870912.0, ('id',), {}, 'acquisition_context', 354, True),
    ':TRIGger:CAN:IDLength': ('enum', ("11BITS","29BITS"), None, None, ('id_length',), {}, 'acquisition_context', 354, True),
    ':TRIGger:CAN:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 355, True),
    ':TRIGger:CAN:THReshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 355, True),
    ':TRIGger:CANFd:BAUDData': ('enum_prefix', ("500kbps","1Mbps","2Mbps","5Mbps","8Mbps","10Mbps","CUSTom"), None, None, ('baud',), {}, 'acquisition_context', 368, True),
    ':TRIGger:CANFd:BAUDNominal': ('enum_prefix', ("10kbps","25kbps","50kbps","100kbps","250kbps","1Mbps","CUSTom"), None, None, ('baud',), {}, 'acquisition_context', 368, True),
    ':TRIGger:CANFd:CONDition': ('enum', ("STARt","REMote","ID","ID_AND_DATA","ERRor"), None, None, ('condition',), {}, 'acquisition_context', 369, True),
    ':TRIGger:CANFd:DAT2': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 369, True),
    ':TRIGger:CANFd:DATA': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 370, True),
    ':TRIGger:CANFd:FTYPe': ('enum', ("BOTH","CAN","CANFd"), None, None, ('frame_type',), {}, 'acquisition_context', 370, True),
    ':TRIGger:CANFd:ID': ('int', (), 0.0, 536870912.0, ('id',), {}, 'acquisition_context', 370, True),
    ':TRIGger:CANFd:IDLength': ('enum', ("11BITS","29BITS"), None, None, ('length',), {}, 'acquisition_context', 371, True),
    ':TRIGger:CANFd:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 371, True),
    ':TRIGger:CANFd:THReshold': ('float', (), None, None, ('threshold',), {}, 'acquisition_context', 372, True),
    ':TRIGger:DELay': ('action', (), None, None, (), {}, 'acquisition_context', 312, False),
    ':TRIGger:DELay:LEVel': ('compound', (), None, None, ('source', 'value'), {}, 'acquisition_context', 313, True),
    ':TRIGger:DELay:LEVel2': ('float', (), None, None, ('level_value',), {}, 'acquisition_context', 314, True),
    ':TRIGger:DELay:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 315, True),
    ':TRIGger:DELay:SLOPe': ('enum', ("RISing","FALLing"), None, None, ('slope_type',), {}, 'acquisition_context', 313, True),
    ':TRIGger:DELay:SLOPe2': ('enum', ("RISing","FALLing"), None, None, ('slope_type',), {}, 'acquisition_context', 313, True),
    ':TRIGger:DELay:SOURce': ('compound', (), None, None, ('state', 'state'), {}, 'acquisition_context', 312, True),
    ':TRIGger:DELay:SOURce2': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 312, True),
    ':TRIGger:DELay:TLOWer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 315, True),
    ':TRIGger:DELay:TUPPer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 316, True),
    ':TRIGger:DROPout': ('action', (), None, None, (), {}, 'acquisition_context', 287, False),
    ':TRIGger:DROPout:COUPling': ('enum', ("DC","AC","LFREJect","HFREJect"), None, None, ('mode',), {}, 'acquisition_context', 287, True),
    ':TRIGger:DROPout:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 287, True),
    ':TRIGger:DROPout:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 288, True),
    ':TRIGger:DROPout:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 288, True),
    ':TRIGger:DROPout:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 289, True),
    ':TRIGger:DROPout:LEVel': ('float', (), None, None, ('level_value',), {}, 'acquisition_context', 289, True),
    ':TRIGger:DROPout:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 290, True),
    ':TRIGger:DROPout:SLOPe': ('any', (), None, None, ('slope_type',), {}, 'acquisition_context', 290, True),
    ':TRIGger:DROPout:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 291, True),
    ':TRIGger:DROPout:TIME': ('float', (), 1e-09, 20.0, ('time',), {}, 'acquisition_context', 291, True),
    ':TRIGger:DROPout:TYPE': ('enum', ("EDGE","STATe"), None, None, ('type',), {}, 'acquisition_context', 292, True),
    ':TRIGger:EDGE': ('action', (), None, None, (), {}, 'acquisition_context', 246, False),
    ':TRIGger:EDGE:COUPling': ('enum', ("DC","AC","LFREJect","HFREJect"), None, None, ('mode',), {}, 'acquisition_context', 246, True),
    ':TRIGger:EDGE:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 246, True),
    ':TRIGger:EDGE:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 247, True),
    ':TRIGger:EDGE:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 247, True),
    ':TRIGger:EDGE:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 248, True),
    ':TRIGger:EDGE:IMPedance': ('enum', ("ONEMeg","FIFTy"), None, None, ('ohm',), {}, 'acquisition_context', 248, True),
    ':TRIGger:EDGE:LEVel': ('float', (), None, None, ('level_value',), {}, 'acquisition_context', 249, True),
    ':TRIGger:EDGE:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 250, True),
    ':TRIGger:EDGE:SLOPe': ('enum', ("RISing","FALLing","ALTernate"), None, None, ('slope_type',), {}, 'acquisition_context', 250, True),
    ':TRIGger:EDGE:SOURce': ('enum', ("C<n>","D<d>","EX","EX5","LINE"), None, None, ('source',), {}, 'acquisition_context', 250, True),
    ':TRIGger:FLEXray:BAUD': ('enum_prefix', ("2500kbps","5Mbps","10Mbps","CUSTom"), None, None, ('baud',), {}, 'acquisition_context', 364, True),
    ':TRIGger:FLEXray:CONDition': ('enum', ("TSS","FRAMe","SYMBol","ERRor"), None, None, ('condition',), {}, 'acquisition_context', 364, True),
    ':TRIGger:FLEXray:FRAMe:COMPare': ('enum', ("ANY","EQUal","GREaterthan","LESSthan"), None, None, ('type',), {}, 'acquisition_context', 365, True),
    ':TRIGger:FLEXray:FRAMe:CYCLe': ('int', (), 0.0, 63.0, ('cycle',), {}, 'acquisition_context', 365, True),
    ':TRIGger:FLEXray:FRAMe:ID': ('int', (), 0.0, 2048.0, ('id',), {}, 'acquisition_context', 365, True),
    ':TRIGger:FLEXray:FRAMe:REPetition': ('enum', ("1","2","4","8","16","32","64"), None, None, ('times',), {}, 'acquisition_context', 366, True),
    ':TRIGger:FLEXray:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 366, True),
    ':TRIGger:FLEXray:THReshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 367, True),
    ':TRIGger:FREQuency': ('action', (), None, None, (), {}, 'acquisition_context', 243, True),
    ':TRIGger:IIC': ('action', (), None, None, (), {}, 'acquisition_context', 329, False),
    ':TRIGger:IIC:ADDRess': ('int', (), 0.0, 1024.0, ('addr',), {}, 'acquisition_context', 329, True),
    ':TRIGger:IIC:ALENgth': ('enum', ("7BIT","10BIT"), None, None, ('length',), {}, 'acquisition_context', 329, True),
    ':TRIGger:IIC:CONDition': ('enum', ("STARt","STOP","RESTart","NACK","EEPRom","7ADDRess","10ADDRess","DLENgth"), None, None, ('condition',), {}, 'acquisition_context', 330, True),
    ':TRIGger:IIC:DAT2': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 330, True),
    ':TRIGger:IIC:DATA': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 330, True),
    ':TRIGger:IIC:DLENgth': ('int', (), 1.0, 12.0, ('length',), {}, 'acquisition_context', 331, True),
    ':TRIGger:IIC:LIMit': ('enum', ("EQUal","GREaterthan","LESSthan"), None, None, ('limit_type',), {}, 'acquisition_context', 331, True),
    ':TRIGger:IIC:RWBit': ('enum', ("WRITe","READ","ANY"), None, None, ('type',), {}, 'acquisition_context', 332, True),
    ':TRIGger:IIC:SCLSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 332, True),
    ':TRIGger:IIC:SCLThreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 333, True),
    ':TRIGger:IIC:SDASource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 333, True),
    ':TRIGger:IIC:SDAThreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 334, True),
    ':TRIGger:IIS:AVARiant': ('enum', ("I2S","LJ","RJ"), None, None, ('type',), {}, 'acquisition_context', 373, True),
    ':TRIGger:IIS:BCLKSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 373, True),
    ':TRIGger:IIS:BCLKThreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 374, True),
    ':TRIGger:IIS:BITorder': ('enum', ("LSB","MSB"), None, None, ('order',), {}, 'acquisition_context', 374, True),
    ':TRIGger:IIS:CHANnel': ('enum', ("LEFT","RIGHT"), None, None, ('channel',), {}, 'acquisition_context', 375, True),
    ':TRIGger:IIS:COMPare': ('enum', ("EQUal","GREaterthan","LESSthan"), None, None, ('type',), {}, 'acquisition_context', 375, True),
    ':TRIGger:IIS:CONDition': ('enum', ("DATA","MUTE","CLIP","GLITch","RISing","FALLing"), None, None, ('condition',), {}, 'acquisition_context', 375, True),
    ':TRIGger:IIS:DLENgth': ('int', (), 1.0, 30.0, ('value',), {}, 'acquisition_context', 376, True),
    ':TRIGger:IIS:DSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 376, True),
    ':TRIGger:IIS:DTHReshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 377, True),
    ':TRIGger:IIS:LATChedge': ('enum', ("RISing","FALLing"), None, None, ('slope',), {}, 'acquisition_context', 378, True),
    ':TRIGger:IIS:LCH': ('enum', ("LOW","HIGH"), None, None, ('level',), {}, 'acquisition_context', 378, True),
    ':TRIGger:IIS:VALue': ('int', (), None, None, ('value',), {}, 'acquisition_context', 379, True),
    ':TRIGger:IIS:WSSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 379, True),
    ':TRIGger:IIS:WSTHreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 380, True),
    ':TRIGger:INTerval': ('action', (), None, None, (), {}, 'acquisition_context', 280, False),
    ':TRIGger:INTerval:COUPling': ('enum', ("DC","AC","LFREJect","HFREJect"), None, None, ('mode',), {}, 'acquisition_context', 280, True),
    ':TRIGger:INTerval:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 280, True),
    ':TRIGger:INTerval:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 281, True),
    ':TRIGger:INTerval:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 281, True),
    ':TRIGger:INTerval:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 282, True),
    ':TRIGger:INTerval:LEVel': ('float', (), None, None, ('level_value',), {}, 'acquisition_context', 282, True),
    ':TRIGger:INTerval:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 283, True),
    ':TRIGger:INTerval:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 284, True),
    ':TRIGger:INTerval:SLOPe': ('any', (), None, None, ('slope_type',), {}, 'acquisition_context', 284, True),
    ':TRIGger:INTerval:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 284, True),
    ':TRIGger:INTerval:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 285, True),
    ':TRIGger:INTerval:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 286, True),
    ':TRIGger:LIN': ('action', (), None, None, (), {}, 'acquisition_context', 357, False),
    ':TRIGger:LIN:BAUD': ('enum_prefix', ("600bps","1200bps","2400bps","4800bps","9600bps","19200bps","CUSTom"), None, None, ('baud',), {}, 'acquisition_context', 357, True),
    ':TRIGger:LIN:CONDition': ('enum', ("BReak","ID","ID_AND_DATA","DATA_ERROR"), None, None, ('condition',), {}, 'acquisition_context', 357, True),
    ':TRIGger:LIN:DAT2': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 358, True),
    ':TRIGger:LIN:DATA': ('int', (), 0.0, 256.0, ('data',), {}, 'acquisition_context', 358, True),
    ':TRIGger:LIN:ERRor:CHECksum': ('enum', ("0","1"), None, None, ('state',), {}, 'acquisition_context', 359, True),
    ':TRIGger:LIN:ERRor:DLENgth': ('int', (), 1.0, 8.0, ('length',), {}, 'acquisition_context', 359, True),
    ':TRIGger:LIN:ERRor:ID': ('int', (), 0.0, 63.0, ('id',), {}, 'acquisition_context', 360, True),
    ':TRIGger:LIN:ERRor:PARity': ('enum', ("0","1"), None, None, ('state',), {}, 'acquisition_context', 360, True),
    ':TRIGger:LIN:ERRor:SYNC': ('enum', ("0","1"), None, None, ('state',), {}, 'acquisition_context', 361, True),
    ':TRIGger:LIN:ID': ('int', (), 0.0, 64.0, ('id',), {}, 'acquisition_context', 361, True),
    ':TRIGger:LIN:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 362, True),
    ':TRIGger:LIN:STANdard': ('enum', ("0","1"), None, None, ('version',), {}, 'acquisition_context', 362, True),
    ':TRIGger:LIN:THReshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 363, True),
    ':TRIGger:MODE': ('enum', ("SINGle","NORMal","AUTO","FTRIG"), None, None, ('mode',), {}, 'acquisition_context', 243, True),
    ':TRIGger:NEDGe': ('action', (), None, None, (), {}, 'acquisition_context', 317, False),
    ':TRIGger:NEDGe:EDGE': ('int', (), 1.0, 65535.0, ('value',), {}, 'acquisition_context', 318, True),
    ':TRIGger:NEDGe:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 320, True),
    ':TRIGger:NEDGe:HLDTime': ('float', (), None, None, ('value',), {}, 'acquisition_context', 320, True),
    ':TRIGger:NEDGe:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 319, True),
    ':TRIGger:NEDGe:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 321, True),
    ':TRIGger:NEDGe:IDLE': ('float', (), 8e-09, 20.0, ('value',), {}, 'acquisition_context', 318, True),
    ':TRIGger:NEDGe:LEVel': ('float', (), None, None, ('level_value',), {}, 'acquisition_context', 319, True),
    ':TRIGger:NEDGe:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 321, True),
    ':TRIGger:NEDGe:SLOPe': ('enum', ("RISing","FALLing"), None, None, ('slope_type',), {}, 'acquisition_context', 317, True),
    ':TRIGger:NEDGe:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 317, True),
    ':TRIGger:PATTern': ('action', (), None, None, (), {}, 'acquisition_context', 301, False),
    ':TRIGger:PATTern:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 301, True),
    ':TRIGger:PATTern:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 301, True),
    ':TRIGger:PATTern:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 302, True),
    ':TRIGger:PATTern:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 302, True),
    ':TRIGger:PATTern:INPut': ('compound', (), None, None, ('logic', 'logic'), {}, 'acquisition_context', 303, True),
    ':TRIGger:PATTern:LEVel': ('compound', (), None, None, ('source', 'value'), {}, 'acquisition_context', 303, True),
    ':TRIGger:PATTern:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 304, True),
    ':TRIGger:PATTern:LOGic': ('enum', ("AND","OR","NAND","NOR"), None, None, ('logic_type',), {}, 'acquisition_context', 305, True),
    ':TRIGger:PATTern:TLOWer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 305, True),
    ':TRIGger:PATTern:TUPPer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 306, True),
    ':TRIGger:PULSe': ('action', (), None, None, (), {}, 'acquisition_context', 260, False),
    ':TRIGger:PULSe:COUPling': ('enum', ("DC","AC","LFREJect","HFREJect"), None, None, ('mode',), {}, 'acquisition_context', 260, True),
    ':TRIGger:PULSe:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 260, True),
    ':TRIGger:PULSe:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 261, True),
    ':TRIGger:PULSe:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 261, True),
    ':TRIGger:PULSe:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 262, True),
    ':TRIGger:PULSe:LEVel': ('float', (), None, None, ('level_value',), {}, 'acquisition_context', 262, True),
    ':TRIGger:PULSe:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 263, True),
    ':TRIGger:PULSe:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 264, True),
    ':TRIGger:PULSe:POLarity': ('enum', ("POSitive","NEGative"), None, None, ('polarity_type',), {}, 'acquisition_context', 264, True),
    ':TRIGger:PULSe:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 264, True),
    ':TRIGger:PULSe:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 265, True),
    ':TRIGger:PULSe:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 266, True),
    ':TRIGger:QUALified': ('action', (), None, None, (), {}, 'acquisition_context', 307, False),
    ':TRIGger:QUALified:ELEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 307, True),
    ':TRIGger:QUALified:ESLope': ('enum', ("RISing","FALLing"), None, None, ('type',), {}, 'acquisition_context', 307, True),
    ':TRIGger:QUALified:ESource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 308, True),
    ':TRIGger:QUALified:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 308, True),
    ':TRIGger:QUALified:QLEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 309, True),
    ':TRIGger:QUALified:QSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 309, True),
    ':TRIGger:QUALified:TLOWer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 310, True),
    ':TRIGger:QUALified:TUPPer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 310, True),
    ':TRIGger:QUALified:TYPE': ('compound', (), None, None, ('type', 'option'), {}, 'acquisition_context', 311, True),
    ':TRIGger:RUN': ('action', (), None, None, (), {}, 'acquisition_context', 244, False),
    ':TRIGger:RUNT': ('action', (), None, None, (), {}, 'acquisition_context', 293, False),
    ':TRIGger:RUNT:COUPling': ('enum', ("DC","AC","LFREJect","HFREJect"), None, None, ('mode',), {}, 'acquisition_context', 293, True),
    ':TRIGger:RUNT:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 293, True),
    ':TRIGger:RUNT:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 294, True),
    ':TRIGger:RUNT:HLEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 294, True),
    ':TRIGger:RUNT:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 295, True),
    ':TRIGger:RUNT:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 296, True),
    ':TRIGger:RUNT:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 296, True),
    ':TRIGger:RUNT:LLEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 297, True),
    ':TRIGger:RUNT:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 297, True),
    ':TRIGger:RUNT:POLarity': ('enum', ("POSitive","NEGative"), None, None, ('polarity_type',), {}, 'acquisition_context', 298, True),
    ':TRIGger:RUNT:SOURce': ('enum', ("C<n>",), None, None, ('source',), {}, 'acquisition_context', 298, True),
    ':TRIGger:RUNT:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 299, True),
    ':TRIGger:RUNT:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 299, True),
    ':TRIGger:SENT:SOURce': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 381, True),
    ':TRIGger:SENT:THReshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 381, True),
    ':TRIGger:SHOLd': ('action', (), None, None, (), {}, 'acquisition_context', 323, False),
    ':TRIGger:SHOLd:CSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 323, True),
    ':TRIGger:SHOLd:CTHReshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 324, True),
    ':TRIGger:SHOLd:DSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 325, True),
    ':TRIGger:SHOLd:DTHReshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 325, True),
    ':TRIGger:SHOLd:LEVel': ('enum', ("LOW","HIGH"), None, None, ('level_state',), {}, 'acquisition_context', 326, True),
    ':TRIGger:SHOLd:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 326, True),
    ':TRIGger:SHOLd:SLOPe': ('any', (), None, None, ('slope_type',), {}, 'acquisition_context', 324, True),
    ':TRIGger:SHOLd:TLOWer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 327, True),
    ':TRIGger:SHOLd:TUPPer': ('float', (), None, None, ('value',), {}, 'acquisition_context', 327, True),
    ':TRIGger:SHOLd:TYPE': ('enum', ("SETup","HOLD"), None, None, ('type',), {}, 'acquisition_context', 323, True),
    ':TRIGger:SLOPe': ('action', (), None, None, (), {}, 'acquisition_context', 252, False),
    ':TRIGger:SLOPe:COUPling': ('enum', ("DC","AC","LFREJect","HFREJect"), None, None, ('mode',), {}, 'acquisition_context', 252, True),
    ':TRIGger:SLOPe:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 252, True),
    ':TRIGger:SLOPe:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 253, True),
    ':TRIGger:SLOPe:HLEVel': ('float', (), None, None, ('high_level_value',), {}, 'acquisition_context', 253, True),
    ':TRIGger:SLOPe:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 254, True),
    ':TRIGger:SLOPe:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 255, True),
    ':TRIGger:SLOPe:LIMit': ('enum', ("LESSthan","GREATerthan","INNer","OUTer"), None, None, ('type',), {}, 'acquisition_context', 255, True),
    ':TRIGger:SLOPe:LLEVel': ('float', (), None, None, ('low_level_value',), {}, 'acquisition_context', 256, True),
    ':TRIGger:SLOPe:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 256, True),
    ':TRIGger:SLOPe:SLOPe': ('enum', ("RISing","FALLing"), None, None, ('slope_type',), {}, 'acquisition_context', 257, True),
    ':TRIGger:SLOPe:SOURce': ('enum', ("C<n>",), None, None, ('source',), {}, 'acquisition_context', 257, True),
    ':TRIGger:SLOPe:TLOWer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 258, True),
    ':TRIGger:SLOPe:TUPPer': ('float', (), 1e-09, 20.0, ('value',), {}, 'acquisition_context', 258, True),
    ':TRIGger:SPI': ('action', (), None, None, (), {}, 'acquisition_context', 335, False),
    ':TRIGger:SPI:BITorder': ('enum', ("LSB","MSB"), None, None, ('bit_order',), {}, 'acquisition_context', 335, True),
    ':TRIGger:SPI:CLKSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 335, True),
    ':TRIGger:SPI:CLKThreshold': ('float', (), None, None, ('clk_threshold',), {}, 'acquisition_context', 336, True),
    ':TRIGger:SPI:CSSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 336, True),
    ':TRIGger:SPI:CSTYpe': ('enum_prefix', ("NCS","CS","TIMeout"), None, None, ('type',), {}, 'acquisition_context', 338, True),
    ':TRIGger:SPI:CSThreshold': ('float', (), None, None, ('threshold',), {}, 'acquisition_context', 337, True),
    ':TRIGger:SPI:DATA': ('compound', (), None, None, ('data', 'data', 'data'), {}, 'acquisition_context', 338, False),
    ':TRIGger:SPI:DLENgth': ('int', (), 4.0, 96.0, ('data_length',), {}, 'acquisition_context', 339, True),
    ':TRIGger:SPI:LATChedge': ('enum', ("RISing","FALLing"), None, None, ('slope',), {}, 'acquisition_context', 339, True),
    ':TRIGger:SPI:MISOSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 339, True),
    ':TRIGger:SPI:MISOThreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 340, True),
    ':TRIGger:SPI:MOSISource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 341, True),
    ':TRIGger:SPI:MOSIThreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 341, True),
    ':TRIGger:SPI:NCSSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 342, True),
    ':TRIGger:SPI:NCSThreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 342, True),
    ':TRIGger:SPI:TTYPe': ('enum', ("MISO","MOSI"), None, None, ('trigger_type',), {}, 'acquisition_context', 343, True),
    ':TRIGger:STATus': ('action', (), None, None, (), {}, 'acquisition_context', 244, True),
    ':TRIGger:STOP': ('action', (), None, None, (), {}, 'acquisition_context', 244, False),
    ':TRIGger:TYPE': ('enum', ("EDGE","PULSE","SLOPe","INTerval","PATTern","RUNT","WINDow","DROPout","VIDeo","QUALified","NEDGe","DELay","SHOLd","IIC","SPI","UART","LIN","CAN","FLEXray","CANFd","IIS","M1553","SENT","A429"), None, None, ('type',), {}, 'acquisition_context', 245, True),
    ':TRIGger:UART': ('action', (), None, None, (), {}, 'acquisition_context', 344, False),
    ':TRIGger:UART:BAUD': ('enum_prefix', ("600bps","1200bps","2400bps","4800bps","9600bps","19200bps","38400bps","57600bps","115200bps","CUSTom"), None, None, ('baud',), {}, 'acquisition_context', 344, True),
    ':TRIGger:UART:BITorder': ('enum', ("LSB","MSB"), None, None, ('order',), {}, 'acquisition_context', 344, True),
    ':TRIGger:UART:CONDition': ('enum', ("STARt","STOP","DATA","ERRor"), None, None, ('condition',), {}, 'acquisition_context', 345, True),
    ':TRIGger:UART:DATA': ('int', (), None, None, ('data',), {}, 'acquisition_context', 345, True),
    ':TRIGger:UART:DLENgth': ('int', (), 5.0, 8.0, ('value',), {}, 'acquisition_context', 346, True),
    ':TRIGger:UART:IDLE': ('enum', ("LOW","HIGH"), None, None, ('idle',), {}, 'acquisition_context', 346, True),
    ':TRIGger:UART:LIMit': ('enum', ("EQUal","GREaterthan","LESSthan"), None, None, ('limit_type',), {}, 'acquisition_context', 347, True),
    ':TRIGger:UART:PARity': ('enum', ("NONE","ODD","EVEN","MARK","SPACe"), None, None, ('parity',), {}, 'acquisition_context', 347, True),
    ':TRIGger:UART:RXSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 348, True),
    ':TRIGger:UART:RXTHreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 348, True),
    ':TRIGger:UART:STOP': ('enum', ("1","1.5","2"), None, None, ('bit',), {}, 'acquisition_context', 349, True),
    ':TRIGger:UART:TTYPe': ('enum', ("RX","TX"), None, None, ('trigger_type',), {}, 'acquisition_context', 349, True),
    ':TRIGger:UART:TXSource': ('enum', ("C<n>","D<d>"), None, None, ('source',), {}, 'acquisition_context', 350, True),
    ':TRIGger:UART:TXTHreshold': ('float', (), None, None, ('value',), {}, 'acquisition_context', 350, True),
    ':TRIGger:VIDeo': ('action', (), None, None, (), {}, 'acquisition_context', 267, False),
    ':TRIGger:VIDeo:FCNT': ('enum', ("1","2","4","8"), None, None, ('field_cnt',), {}, 'acquisition_context', 267, True),
    ':TRIGger:VIDeo:FIELd': ('enum', ("1","2"), None, None, ('field',), {}, 'acquisition_context', 267, True),
    ':TRIGger:VIDeo:FRATe': ('any', (), None, None, ('frate',), {}, 'acquisition_context', 268, True),
    ':TRIGger:VIDeo:INTerlace': ('any', (), None, None, ('interlace',), {}, 'acquisition_context', 268, True),
    ':TRIGger:VIDeo:LCNT': ('int', (), 300.0, 2000.0, ('line_cnt',), {}, 'acquisition_context', 268, True),
    ':TRIGger:VIDeo:LEVel': ('float', (), None, None, ('level_value',), {}, 'acquisition_context', 269, True),
    ':TRIGger:VIDeo:LINE': ('int', (), 1.0, 263.0, ('line',), {}, 'acquisition_context', 270, True),
    ':TRIGger:VIDeo:SOURce': ('enum', ("C<n>",), None, None, ('source',), {}, 'acquisition_context', 270, True),
    ':TRIGger:VIDeo:STANdard': ('enum', ("NTSC","PAL","P720L50","P720L60","P1080L50","P1080L60","I1080L50","I1080L60","CUSTom"), None, None, ('standard',), {}, 'acquisition_context', 271, True),
    ':TRIGger:VIDeo:SYNC': ('enum', ("SELect","ANY"), None, None, ('sync',), {}, 'acquisition_context', 271, True),
    ':TRIGger:WINDow': ('action', (), None, None, (), {}, 'acquisition_context', 273, False),
    ':TRIGger:WINDow:CLEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 273, True),
    ':TRIGger:WINDow:COUPling': ('enum', ("DC","AC","LFREJect","HFREJect"), None, None, ('mode',), {}, 'acquisition_context', 273, True),
    ':TRIGger:WINDow:DLEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 274, True),
    ':TRIGger:WINDow:HLDEVent': ('int', (), 1.0, 100000000.0, ('value',), {}, 'acquisition_context', 275, True),
    ':TRIGger:WINDow:HLDTime': ('float', (), 8e-09, 30.0, ('value',), {}, 'acquisition_context', 275, True),
    ':TRIGger:WINDow:HLEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 276, True),
    ':TRIGger:WINDow:HOLDoff': ('enum', ("OFF","EVENts","TIME"), None, None, ('holdoff_type',), {}, 'acquisition_context', 276, True),
    ':TRIGger:WINDow:HSTart': ('enum', ("LAST_TRIG","ACQ_START"), None, None, ('start_holdoff',), {}, 'acquisition_context', 277, True),
    ':TRIGger:WINDow:LLEVel': ('float', (), None, None, ('value',), {}, 'acquisition_context', 277, True),
    ':TRIGger:WINDow:NREJect': ('enum', ("OFF","ON"), None, None, ('state',), {}, 'acquisition_context', 278, True),
    ':TRIGger:WINDow:SOURce': ('enum', ("C<n>",), None, None, ('source',), {}, 'acquisition_context', 279, True),
    ':TRIGger:WINDow:TYPE': ('enum', ("ABSolute","RELative"), None, None, ('type',), {}, 'acquisition_context', 279, True),
}

CATALOG = {
    key: CommandSpec(key, kind, choices, minimum, maximum, args,
                     indices, risk, page, has_query)
    for key, (kind, choices, minimum, maximum, args, indices, risk, page, has_query)
    in RAW.items()
}


_BY_UPPER = {key.upper(): key for key in RAW}


def _literal(segment: str) -> str:
    """Match a segment by its documented short form, as SCPI itself does."""
    short = segment[: len(segment) - len(segment.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]
    return re.escape(short or segment) + "[A-Za-z0-9]*"


def _pattern(key: str) -> "re.Pattern[str]":
    parts = []
    for segment in key.split(":"):
        match = re.search(r"<([a-z])>", segment)
        if match:
            parts.append(
                _literal(segment[: match.start()])
                + "(?P<" + match.group(1) + ">[A-Za-z0-9]+)"
            )
        else:
            parts.append(_literal(segment))
    return re.compile("^" + ":".join(parts) + "$", re.IGNORECASE)


# Longest documented spelling first, so the most specific entry wins.
_PATTERNS = sorted(
    ((_pattern(key), key) for key in RAW),
    key=lambda item: -len(item[0].pattern),
)


def lookup(command: str) -> "tuple[CommandSpec, dict[str, str]] | None":
    """Resolve a concrete command to its catalog entry and captured indices."""
    text = command.strip().rstrip("?").strip()
    if not text.startswith(":"):
        text = ":" + text
    key = _BY_UPPER.get(text.upper())
    if key is not None:
        return CATALOG[key], {}
    for pattern, candidate in _PATTERNS:
        match = pattern.match(text)
        if match:
            return CATALOG[candidate], {k: v for k, v in match.groupdict().items() if v}
    return None


def render(spec: "CommandSpec") -> str:
    """One-line summary used by ``configure_scope.py list``."""
    if spec.kind == "enum":
        domain = " | ".join(spec.choices)
    elif spec.kind == "enum_prefix":
        domain = " | ".join(spec.choices) + " [,<value>]"
    elif spec.kind in ("int", "float", "number"):
        if spec.minimum is None or spec.maximum is None:
            domain = "<number>"
        else:
            domain = "[%g, %g]" % (spec.minimum, spec.maximum)
    elif spec.kind == "string":
        domain = '"<quoted text or path>"'
    elif spec.kind == "compound":
        domain = "<" + ">,<".join(spec.args) + ">"
    elif spec.kind == "action":
        domain = "(no argument)"
    else:
        domain = "<value>"
    index = ", ".join(
        "%s=%s" % (name, "/".join(values) if values else "n")
        for name, values in spec.indices.items()
    )
    return "%-42s %-9s %s%s%s" % (
        spec.command,
        spec.risk,
        domain,
        ("  [%s]" % index) if index else "",
        ("  query" if spec.has_query else "  NO-READBACK")
        + ("  p.%d" % spec.page),
    )
