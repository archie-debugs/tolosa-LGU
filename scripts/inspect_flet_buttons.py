import flet
print('flet version:', getattr(flet, '__version__', 'unknown'))
for name in sorted(dir(flet)):
    if name.endswith('Button'):
        print(name)
print('\nOther available classes:')
for name in ['Icon', 'Icons', 'TextButton', 'OutlinedButton', 'FilledButton', 'ElevatedButton', 'PopupMenuButton', 'IconButton']:
    print(name, hasattr(flet, name))
