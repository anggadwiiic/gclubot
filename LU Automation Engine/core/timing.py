import random
import time


def human_pause(minimum=1.6, maximum=2.4):
    time.sleep(random.uniform(minimum, maximum))
