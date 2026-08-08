import flet, inspect
print('type:', type(flet.Padding))
try:
    print('signature:', inspect.signature(flet.Padding))
except Exception as e:
    print('signature error:', e)
print('has only:', hasattr(flet.Padding, 'only'))
print('has symmetric:', hasattr(flet.Padding, 'symmetric'))
print('repr:', repr(flet.Padding))
print('callable:', callable(flet.Padding))
