"""Windows GPU engine performance counters; no vendor-specific driver required."""
import ctypes
from ctypes import wintypes
class GPUStats:
 def __init__(self):self.query=None;self.counter=None
 def read(self):
  try:
   pdh=ctypes.WinDLL('pdh');ptr=ctypes.c_void_p
   if self.query is None:
    q=ptr();c=ptr()
    if pdh.PdhOpenQueryW(None,0,ctypes.byref(q)):return '—'
    if pdh.PdhAddEnglishCounterW(q,r'\\GPU Engine(*)\\Utilization Percentage',0,ctypes.byref(c)):
     pdh.PdhCloseQuery(q);return '—'
    self.query=q;self.counter=c;pdh.PdhCollectQueryData(q);return '—'
   if pdh.PdhCollectQueryData(self.query):return '—'
   size=wintypes.DWORD();count=wintypes.DWORD()
   pdh.PdhGetFormattedCounterArrayW(self.counter,0x200,ctypes.byref(size),ctypes.byref(count),None)
   if not size.value:return '—'
   buf=ctypes.create_string_buffer(size.value)
   if pdh.PdhGetFormattedCounterArrayW(self.counter,0x200,ctypes.byref(size),ctypes.byref(count),buf):return '—'
   class Value(ctypes.Structure):_fields_=[('status',wintypes.DWORD),('value',ctypes.c_double)]
   class Item(ctypes.Structure):_fields_=[('name',ctypes.c_wchar_p),('value',Value)]
   items=ctypes.cast(buf,ctypes.POINTER(Item));engines={}
   for i in range(count.value):
    item=items[i]
    if item.value.status not in (0,1):continue
    key=(item.name or '').split('_',2)[-1];engines[key]=engines.get(key,0)+item.value.value
   return f'{min(100,max(engines.values(),default=0)):.0f}%'
  except Exception:return '—'
