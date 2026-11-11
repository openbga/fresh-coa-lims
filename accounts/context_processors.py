def account_navigation(request):
    return {
        "can_manage_accounts": request.user.is_authenticated
        and request.user.is_active
        and request.user.groups.filter(name="admin").exists()
    }
