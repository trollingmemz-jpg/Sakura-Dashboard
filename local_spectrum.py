"""Local Spotify PCM spectrum, independent of Sakura Connect."""
import math
import time
from array import array
try:
 import numpy as np
except ImportError:
 np=None

RATE=48000
N=4096
BANDS=80
WINDOW=[.5-.5*math.cos(2*math.pi*i/(N-1)) for i in range(N)]
EDGES=[max(1,min(N//2,round(40*(16000/40)**(i/BANDS)*N/RATE))) for i in range(BANDS+1)]

def fft_power(samples):
 if np is not None:
  a=np.asarray(samples,dtype=np.float32).reshape(-1,2)
  f=np.fft.rfft(a*np.asarray(WINDOW)[:,None],axis=0)
  return np.sqrt(np.mean(abs(f)**2,axis=1))*4/N
 # Dependency-free fallback: FFT of mono PCM.
 a=[complex((samples[2*i]+samples[2*i+1])*.5*WINDOW[i]) for i in range(N)]
 j=0
 for i in range(1,N):
  bit=N>>1
  while j&bit:j^=bit;bit>>=1
  j^=bit
  if i<j:a[i],a[j]=a[j],a[i]
 m=2
 while m<=N:
  step=complex(math.cos(-2*math.pi/m),math.sin(-2*math.pi/m))
  for k in range(0,N,m):
   w=1
   for j in range(k,k+m//2):
    u=a[j];v=w*a[j+m//2];a[j]=u+v;a[j+m//2]=u-v;w*=step
  m*=2
 return [abs(x)*4/N for x in a[:N//2+1]]

class LiveSpectrum:
 def __init__(self):
  self.pcm=b'';self.bars=[0.]*BANDS;self.last=0.;self.dirty=False
 def reset(self):
  self.pcm=b'';self.bars=[0.]*BANDS;self.last=0.;self.dirty=False
 def feed(self,data):
  self.pcm=(self.pcm+data)
  if len(self.pcm)>N*8:
   drop=((len(self.pcm)-N*4)//4)*4;self.pcm=self.pcm[drop:]
  if data:self.last=time.monotonic();self.dirty=True
 def tick(self):
  target=[0.]*BANDS
  if self.dirty and len(self.pcm)>=N*4 and time.monotonic()-self.last<.3:
   end=len(self.pcm)//4*4
   samples=array('h');samples.frombytes(self.pcm[end-N*4:end])
   import sys
   if sys.byteorder!='little':samples.byteswap()
   power=fft_power(samples)
   for i in range(BANDS):
    lo=EDGES[i];hi=max(lo+1,EDGES[i+1])
    peak=max(power[lo:hi],default=0)/32768
    db=20*math.log10(max(peak,1e-8))
    target[i]=max(0.,min(1.,(db+65)/60))
   self.dirty=False
  elif time.monotonic()-self.last<.2:
   return self.bars
  self.bars=[a+(b-a)*(.75 if b>a else .38) for a,b in zip(self.bars,target)]
  return self.bars
