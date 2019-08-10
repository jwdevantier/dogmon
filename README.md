# Dogmon

**BEWARE**: quick hack written to solve an immediate problem.

## What
Needed to monitor how our dog was doing when left alone. Being a nerd, I could not possibly use normal-people solutions like dialing from skype or similar, but I also didn't have a month or more to make something.

This is the result. Configure your cameras and the interval and dogmon will snap a picture from each camera once every 60 seconds and attempt sending it off as an email and upload it to dropbox.

This isn't configurable and it should be, but fork and customize to your situation. Otherwise, take it as an amusing example of what emerges when coding python in panic (I'm trademarking that!).


## Use

    $ python3 -m venv venv
    $ source venv/bin/activate
    (venv)$ pip install -r requirements.txt 