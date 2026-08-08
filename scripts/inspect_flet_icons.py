import flet
print('flet version:', getattr(flet, '__version__', 'unknown'))
print('has icons attr', hasattr(flet, 'icons'))
print('module attrs contains icons:', 'icons' in dir(flet))
print('available icons module path:', getattr(flet, 'icons', None))
try:
    import flet.icons as icons
    print('flet.icons loaded:', icons)
    print('icon attr sample:', [n for n in dir(icons) if n.isupper()][:80])
except Exception as e:
    print('failed to import flet.icons:', e)
