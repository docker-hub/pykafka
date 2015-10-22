import atexit


def unregister_cleanup_func(cleanup, obj):
    """Unregister the cleanup handler"""
    if hasattr(obj, '_cleanup_func'):
        # Remove cleanup handler now that we've stopped
        try:
            # py3 supports unregistering
            if hasattr(atexit, 'unregister'):
                atexit.unregister(cleanup) # pylint: disable=no-member
            # py2 requires removing from private attribute...
            else:
                # ValueError on list.remove() if the exithandler no longer exists
                # but that is fine here
                atexit._exithandlers.remove((cleanup, (obj,), {}))
        except ValueError:
            pass


def register_cleanup_func(cleanup, obj):
    """Register a cleanup handler"""
    atexit.register(cleanup, obj)
