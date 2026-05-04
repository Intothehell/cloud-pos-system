from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    # Delete all existing users
    User.query.delete()
    
    # Create new users
    users_data = [
        {'username': 'loshan', 'email': 'loshan@easypay.com', 'password': 'HiMary9089', 'role': 'owner'},
        {'username': 'manager', 'email': 'manager@easypay.com', 'password': 'glass#1324', 'role': 'manager'},
        {'username': 'milintha', 'email': 'milintha@easypay.com', 'password': 'milintha@001', 'role': 'staff'},
        {'username': 'eranga', 'email': 'eranga@easypay.com', 'password': '002@eran', 'role': 'staff'},
    ]
    
    for data in users_data:
        user = User(
            username=data['username'],
            email=data['email'],
            role=data['role']
        )
        user.set_password(data['password'])
        db.session.add(user)
        print(f"Created: {data['username']}")
    
    db.session.commit()
    print("Done!")