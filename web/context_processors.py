from .tournament_ops import can_operate


def navigation(request):
    return {'is_management_user': can_operate(request.user)}
