
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email import encoders
from datetime import datetime
from pathlib import Path
from os import path
import typing as t
from time import sleep
import configparser

import cv2
from apscheduler.schedulers.background import BackgroundScheduler
import dropbox
import time


class DropboxFolder:
    def __init__(self, access_token, destination_folder: Path):
        self.access_token = access_token
        self.destination_folder = destination_folder

    def upload_file(self, file_from: Path, filename: t.Optional[str] = None):
        """upload a file to Dropbox using API v2
        """
        if not filename:
            filename = file_from.name


        dbx = dropbox.Dropbox(self.access_token)

        with open(file_from, 'rb') as f:
            retry=5
            while True:
                try:
                    dbx.files_upload(
                        f.read(), Path(self.destination_folder, filename).as_posix(),
                        mode=dropbox.files.WriteMode.overwrite)
                    break
                except dropbox.exceptions.ApiError as e:
                    print(f"Dropbox API error: {repr(e)}")
                    time.sleep(5)
                    retry -= 1



def parse_list_str(list_str):
    return [e.strip() for e in list_str.split(',')] if isinstance(list_str, str) else list_str


def determine_cameras():
    cams = []
    for i in range(0, 10):
        cap = cv2.VideoCapture(i)
        if cap.read()[0]:
            cams.append(i)
        cap.release()
    return cams


class EmailConf:
    def __init__(self, conf: t.Dict[str, t.Any]):
        self.account = EmailAccount(conf['account']) 
        self.recipients = parse_list_str(conf['message']['recipients'])
    
    def __repr__(self):
        return f"EmailConf<account: {repr(self.account)}, recipients: {repr(self.recipients)}>"


class EmailAccount:
    def __init__(self, conf: t.Dict['str', t.Any]):

        self.email = conf['email']
        self.password = conf['password']
        self.username = conf.get('username', self.email)
        self.server = conf['server']
        self.port = conf['port']
    
    def __repr__(self):
        return ("EmailAccount<"
            f"email: {self.email}, "
            f"password: {'******' if self.password else '-UNSET-'}, "
            f"username: {self.username}, "
            f"server: {self.server}, "
            f"port: {self.port}"
            ">")


class ImageConf:
    def __init__(self, conf: t.Dict[str, t.Any]):
        cameras = [int(cam) for cam in parse_list_str(conf['image']['cameras'])]
        connected_cameras = determine_cameras()
        if set(cameras) - set(connected_cameras):
            missing_cameras = set(cameras) - set(connected_cameras)
            raise RuntimeError(f"Config mentions non-existing cameras '{repr(list(missing_cameras))}', cameras found: '{repr(connected_cameras)}'")
        self.cameras = cameras
        self.interval = int(conf['image']['interval'])
        self.imgdir = Path(path.expanduser(conf['image']['imgdir']))

    def __repr__(self):
        return (
            f"{type(self).__name__}<"
            f"cameras: {repr(self.cameras)}, "
            f"interval: {self.interval}, "
            f"imgdir: {self.imgdir}"
            ">")

class DropboxConf:
    def __init__(self, conf: t.Dict[str, t.Any]):
        self.access_token = conf['account']['access_token']
        self.destination = conf['account']['to_path']
        self.folder = DropboxFolder(self.access_token, self.destination)
    
    def __repr__(self):
        return (
            f"{type(self).__name__}<"
            f"access_token: {'*****' if self.access_token else '<UNSET>'}, "
            f"destination: {self.destination}"
            ">"
        )

class Conf:
    def __init__(self, conf: t.Dict[str, t.Any]):
        self.image = conf['image']
        self.email = conf['email']
        self.dropbox = conf['dropbox']
    
    def __repr__(self):
        return (
            f"{type(self).__name__}<"
            f"email: {self.email}, "
            f"image: {self.image}, "
            f"dropbox: {self.dropbox}"
            ">"
        )

conf_classes = {
    'email': EmailConf,
    'image': ImageConf,
    'dropbox': DropboxConf,
}
def read_config():
    conf = {}
    for label, ini_file in [('email', 'email.ini'), ('image', 'image.ini'), ('dropbox', 'dropbox.ini')]:
        cp = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
        cp.read(ini_file)
        d_config = {s: dict(cp.items(s)) for s in cp.sections()}
        conf_class = conf_classes.get(label, None)
        conf[label] = conf_class(d_config) if conf_class is not None else d_config
    return Conf(conf)


def create_img_attachment(fpath: Path) -> MIMEBase:
    with open(fpath.as_posix(), 'rb') as img:
        return MIMEImage(img.read(), name=fpath.name)


def sendmail(account: EmailAccount, to_addrs: t.List[str], msg: MIMEBase):
    s = smtplib.SMTP(account.server, account.port)
    s.starttls()
    # print(f"logging in as '{account.username}, using password: '{account.password}'...'")
    s.login(account.username, account.password)
    msg['From'] = account.email
    # msg['To'] = to_addrs # TODO: is this even necessary ?
    
    s.sendmail(account.email, to_addrs, msg.as_string())
    s.quit()


def create_email(now: datetime) -> MIMEBase:
    """

    NOTE: remember to set msg['From'] and msg['To']
    """
    msg = MIMEMultipart()
    # Short date format, e.g. 'Sunday (28/07) - 14:08'
    msg['Subject'] = f"{now.strftime('%A (%d/%m) - %H:%M')}"
    
    # Human-readable date format, e.g. 'Picture taken at 14:08, Sunday July 28, 2019
    body = f"""Picture taken at {now.strftime('%-H:%M, %A %B %-d, %Y')}"""
    msg.attach(MIMEText(body, 'plain'))
    return msg


def capture_image(imgpath: Path, cam_id: int):
    camera = cv2.VideoCapture(cam_id)
    return_value, image = camera.read()
    cv2.imwrite(imgpath.as_posix(), image)
    del(camera)

def capture_images(conf: Conf) -> t.List[Path]:
    now = datetime.now()
    img_paths = []
    for cam_id in conf.image.cameras:
        img_path = Path(conf.image.imgdir, f"{now.strftime('%m-%d %H:%M')}-cam{cam_id}.png")
        img_paths.append(img_path)
        capture_image(img_path, cam_id)

    return img_paths

def send_email(conf: Conf, images: t.List[Path]) -> None:
    now = datetime.now()
    email = create_email(now)
    for img_path in images:
        email.attach(create_img_attachment(img_path))
    sendmail(conf.email.account, conf.email.recipients, email)


def send_dropbox(conf: Conf, images: t.List[Path]) -> None:
    for img_path in images:
        conf.dropbox.folder.upload_file(img_path)

def loop_task(conf: Conf):
    img_paths = capture_images(conf)
    try:
        send_email(conf, img_paths)
    except Exception as e:
        print(f"email err: {repr(e)}")
    try:
        send_dropbox(conf, img_paths)
    except Exception as e:
        print(f"dropbox err: {repr(e)}")
    print("!", flush=True, end='')

def main(conf: Conf):
    conf.image.imgdir.mkdir(parents=True, exist_ok=True)

    loop_task(conf)

    scheduler = BackgroundScheduler()
    scheduler.start()

    scheduler.add_job(loop_task, 'interval', seconds=conf.image.interval, args=[conf])
    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("\nexiting...")


def testfn():
    index = 0
    arr = []
    while True:
        cap = cv2.VideoCapture(index)
        if not cap.read()[0]:
            break
        else:
            arr.append(index)
        cap.release()
        index += 1
    return arr



if __name__ == "__main__":
    c = read_config()
    print("CONFIG")
    print(c)
    main(c)
