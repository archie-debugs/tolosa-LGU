import flet, inspect
print('has BorderSide:', hasattr(flet, 'BorderSide'))
if hasattr(flet, 'BorderSide'):
    print('BorderSide repr', repr(flet.BorderSide))
    try:
        print('BorderSide sig', inspect.signature(flet.BorderSide))
    except Exception as e:
        print('sig err', e)
else:
    print('No BorderSide')
