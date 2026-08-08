import flet
print('flet version:', getattr(flet, '__version__', 'unknown'))
print('has run:', hasattr(flet, 'run'))
print('has app:', hasattr(flet, 'app'))
print('has Button:', hasattr(flet, 'Button'))
print('has TextButton:', hasattr(flet, 'TextButton'))
print('has OutlinedButton:', hasattr(flet, 'OutlinedButton'))
print('has Icons:', hasattr(flet, 'Icons'))
print('has icon module:', 'icons' in dir(flet))
try:
    import flet.icons as icons
    print('icons module loaded, sample:', [n for n in dir(icons) if n.isupper()][:40])
except Exception as e:
    print('icons module failed:', e)
print('button attrs:', [name for name in dir(flet) if 'Button' in name])
print('other attrs:', [name for name in dir(flet) if 'ICON' in name.upper()][:40])
