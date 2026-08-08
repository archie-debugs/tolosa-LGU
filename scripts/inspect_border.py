import flet, inspect
print('flet version:', getattr(flet, '__version__', 'unknown'))
print('has Border:', hasattr(flet, 'Border'))
if hasattr(flet, 'Border'):
    print('Border repr:', repr(flet.Border))
    try:
        print('Border dir sample:', [n for n in dir(flet.Border) if 'all' in n.lower() or n.islower()][:200])
        print('signature:', inspect.signature(flet.Border))
    except Exception as e:
        print('inspect error', e)
else:
    print('No Border in flet')
