from app.models.customer import Notification
from app.models.user import User


def create_notification(db, user_id: int, kind: str, title: str, message: str) -> None:
    db.add(Notification(user_id=user_id, kind=kind, title=title, message=message))


def notify_admins(db, kind: str, title: str, message: str) -> None:
    admin_ids = db.query(User.id).filter(User.is_admin.is_(True)).all()
    for (admin_id,) in admin_ids:
        create_notification(db, admin_id, kind, title, message)
