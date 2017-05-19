import requests, time, re, redis
API_BASE_URL = 'https://hacker-news.firebaseio.com/v0/'
RATE_LIMIT = 20

def ratelimit(max_per_second):
    min_interval = 1.0 / float(max_per_second)
    def decorate(func):
        last_time_called = [0.0]
        def rate_limited_function(*args, **kargs):
            elapsed = time.clock() - last_time_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kargs)
            last_time_called[0] = time.clock()
            return ret
        return rate_limited_function
    return decorate

class UserGetter():
    def __init__(self):
        self.users = {} # user_id: { karma: 0, favorites: [] }
        self.redis = redis.StrictRedis(host = 'localhost', port = 6379, db = 0)
        self.__karma_threshold = 500
        self.__got_user_info = False

    def store_users(self):
        if not self.__got_user_info:
            return

        for user in self.users:
            self.redis.hmset('users:'+user, self.users[user])

    def get_top_post_users(self):
        top_post_ids = requests.get(API_BASE_URL + 'topstories.json').json()
        for post_id in top_post_ids[:25]:
            self.get_users(post_id)

    def get_users(self, post_id):
        try:
            post_json = self.get_item_json('item', post_id)
            if post_json:
                if 'by' in post_json: # Deleted posts don't have author
                    self.users[post_json['by']] = {'karma': 0} # Store the user

                if not 'kids' in post_json:
                    return
                else:
                    for kid in post_json['kids']:
                        self.get_users(kid)
            else:
                print('ERROR: No post JSON: {0}'.format(post_id))
        except:
            print('ERROR: get_users try catch: {0}'.format(post_id))

    def get_users_info(self):
        for user_id in self.users.keys():
            if self.users[user_id]['karma'] == 0: # Don't get already fetched (?)
                user_json = self.get_item_json('user', user_id)
                if user_json and 'karma' in user_json and user_json['karma'] > self.__karma_threshold:
                    self.users[user_id]['karma'] = user_json['karma']
                    self.users[user_id]['favorites'] = self.get_user_favorites(user_id)
                else:
                    self.users.pop(user_id, None)

        self.__got_user_info = True

    @ratelimit(RATE_LIMIT)
    def get_item_json(self, item_type, item_id):
        return requests.get(API_BASE_URL + '{0}/{1}.json'.format(item_type, item_id)).json()

    @ratelimit(RATE_LIMIT)
    def get_user_favorites(self, user_id):
        favorites = []
        story_regex = r"<tr class='athing' id='([0-9]+)'"
        for page in range(1, 10): #TODO: Only get next page if 'More' link
            profile_text = requests.get('https://news.ycombinator.com/favorites?id={0}&p={1}'.format(user_id, page)).text
            matches = re.findall(story_regex, profile_text)
            if not matches:
                break
            else:
                favorites = favorites + matches
        return favorites


if __name__ == "__main__":
    ug = UserGetter()
    ug.get_top_post_users()
    ug.get_users_info()
    ug.store_users()
    # print(ug.users)