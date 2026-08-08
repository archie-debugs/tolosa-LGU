import flet
print('flet version:', getattr(flet, '__version__', 'unknown'))
print('Alignment in flet:', hasattr(flet, 'Alignment'))
if hasattr(flet, 'Alignment'):
    print('Alignment dir:', [n for n in dir(flet.Alignment) if n.isupper() or n.islower()][:200])
print('has alignment attr', hasattr(flet, 'alignment'))
if hasattr(flet, 'alignment'):
    print('alignment module dir:', [n for n in dir(flet.alignment) if n.isupper() or n.islower()][:200])
