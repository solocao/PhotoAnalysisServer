import datetime

from fastapi.security import OAuth2PasswordRequestForm
from typing import Optional
from jose import JWTError, jwt
from starlette import status

from db_connection import get_user_by_name_db, add_user_db, set_user_roles_db

from dependency import pwd_context, logger, oauth2_scheme, TokenData, User, CredentialException, Roles
from fastapi import APIRouter, Depends, HTTPException

auth_router = APIRouter()

# to get a string like this run: openssl rand -hex 32
SECRET_KEY = "22013516088ae490602230e8096e61b86762f60ba48a535f0f0e2af32e87decd"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60*16  # 16 Hour Expiration


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str):
    user = get_user_by_name_db(username)
    if not user:
        return False
    if not verify_password(password, user.password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise CredentialException()
        token_data = TokenData(username=username)
    except JWTError:
        raise CredentialException()
    user = get_user_by_name_db(username=token_data.username)
    if user is None:
        raise CredentialException()
    return user


async def get_current_active_user(current_user=Depends(get_current_user)):
    logger.debug('Current User Disabled:' + str(current_user.disabled))
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def current_user_investigator(token: str = Depends(oauth2_scheme)):
    """
    Permission Checking Function to be used as a Dependency
    :param token: User authentication token
    :return: User has sufficient permissions
    """
    user = get_current_user(token)
    if not any(role in [Roles.admin.name, Roles.investigator.name] for role in user.roles):
        logger.debug('User Roles')
        logger.debug(user.roles)

        raise CredentialException()

    return user


async def current_user_researcher(token: str = Depends(oauth2_scheme)):
    """
    Permission Checking Function to be used as a Dependency
    :param token: User authentication token
    :return: User has sufficient permissions
    """
    user = get_current_user(token)
    if not any(role in [Roles.admin.name, Roles.researcher.name] for role in user.roles):
        raise CredentialException()

    return user


async def current_user_admin(token: str = Depends(oauth2_scheme)):
    """
    Permission Checking Function to be used as a Dependency
    :param token: User authentication token
    :return: User has sufficient permissions
    """
    user = get_current_user(token)
    if Roles.admin.name not in user.roles:
        raise CredentialException()

    return user


# -------------------------------------------------------------------------------
#
#           User Authentication Endpoints
#
# -------------------------------------------------------------------------------

@auth_router.post('/add_role', dependencies=[Depends(current_user_admin)])
async def add_permission_to_user(username, new_role):
    user = get_user_by_name_db(username)
    if not user:
        return {'status': 'failure', 'detail': 'User does not exist. Unable to modify permissions.'}

    # Ensure that the role name is valid
    if new_role not in list(Roles.__members__):
        return {'status': 'failure', 'detail': 'Role specified does not exist. Unable to modify permissions.'}

    if new_role in user.roles:
        return {'status': 'success',
                'detail': 'User ' + str(username) + ' already has role ' + str(new_role) + '. No changes made.'}

    user_new_role_list = user.roles.copy()
    user_new_role_list.append(new_role)
    set_user_roles_db(username, user_new_role_list)
    return {'status': 'success',
            'detail': 'User ' + str(username) + ' added to role ' + str(new_role) + '.'}


@auth_router.post('/remove_role', dependencies=[Depends(current_user_admin)])
async def remove_permission_from_user(username, new_role):
    user = get_user_by_name_db(username)
    if not user:
        return {'status': 'failure', 'detail': 'User does not exist. Unable to modify permissions.'}

    # Ensure that the role name is valid
    if new_role not in list(Roles.__members__):
        return {'status': 'failure', 'detail': 'Role specified does not exist. Unable to modify permissions.'}

    if new_role not in user.roles:
        return {'status': 'success',
                'detail': 'User ' + str(username) + ' does not have role ' + str(new_role) + '. No changes made.'}

    user_new_role_list = user.roles.copy()
    user_new_role_list.remove(new_role)
    set_user_roles_db(username, user_new_role_list)
    return {'status': 'success',
            'detail': 'User ' + str(username) + ' removed from role ' + str(new_role) + '.'}


@auth_router.post("/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"status": 'success',
            'detail': 'Successfully Logged In.',
            "access_token": access_token,
            "token_type": "bearer"
            }


@auth_router.post('/new/')
def create_account(username, password, email=None, full_name=None, agency=None):
    u = User(
        username=username,
        password=get_password_hash(password),
        email=email,
        full_name=full_name,
        roles=[],
        agency=agency
    )
    return add_user_db(u)


@auth_router.get("/status/", dependencies=[Depends(get_current_active_user)])
async def get_login_status():
    """
    Check if the user is authenticated currently
    :return: Cleaned user profile
    """

    return {'status': 'success', 'detail': 'User is Authenticated.'}


@auth_router.get("/profile/")
async def get_current_user_profile(current_user: User = Depends(get_current_active_user)):
    """
    Export the data of the current user to the client
    :param current_user: Currently logged in user to have data exported
    :return: Cleaned user profile
    """
    user_export_data = current_user.dict(exclude={'password', 'id'})
    return user_export_data
