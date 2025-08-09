from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True
            
        # Write permissions are only allowed to the owner of the lunchbox.
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'lunchbox'):
            return obj.lunchbox.owner == request.user
            
        return False


class IsLunchboxOwner(permissions.BasePermission):
    """
    Permission to only allow owners of a lunchbox to access it.
    """
    def has_permission(self, request, view):
        # For list/create views, check if the user is authenticated
        if not request.user.is_authenticated:
            return False
            
        # For detail/update/delete views, check object ownership
        if hasattr(view, 'get_object'):
            obj = view.get_object()
            if hasattr(obj, 'owner'):
                return obj.owner == request.user
            elif hasattr(obj, 'lunchbox'):
                return obj.lunchbox.owner == request.user
                
        return True


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    The request is authenticated as an admin user, or is a read-only request.
    """
    def has_permission(self, request, view):
        return bool(
            request.method in permissions.SAFE_METHODS or
            (request.user and request.user.is_staff)
        )


class IsOwner(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to access it.
    """
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'lunchbox'):
            return obj.lunchbox.owner == request.user
        return False
