import httpx, inspect
print('httpx version:', getattr(httpx, '__version__', 'unknown'))
print('httpx.Client.__init__ signature:', inspect.signature(httpx.Client.__init__))
print('httpx.Client.__init__ defaults:', httpx.Client.__init__.__defaults__)
