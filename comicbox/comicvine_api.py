import pkg_resources
import regex
import requests

from .metadata.comicvine import ComicVine


# TODO rate limit!
# TODO handle responses
# TODO cache volumes on disk
# TODO searching
# TODO searching cli

VERSION = pkg_resources.get_distribution("comicbox").version


class ComicVineTypeID:
    VOLUME = "4050"
    ISSUE = "4000"


CV_STATUS_CODES = {
    1: "OK",
    100: "Invalid API Key",
    101: "Object Not Found",
    102: "Error in URL Format",
    103: "'jsonp' format requires a 'json_callback' argument",
    104: "Filter Error",
    105: "Subscriber only video is for subscribers only",
}


class ComicVineAPI:

    BASE_URL = "https://comicvine.gamespot.com/api/"
    ISSUE_FIELDS = (
        "character_credits",
        "cover_date",
        "deck",
        "description",
        "id",
        "issue_number",
        "location_credits",
        "name",
        "person_credits",
        "site_detail_url",
        "story_arc_credits",
        "team_credits",
        "volume",
    )
    VOLUME_FIELDS = ("id", "publisher", "name", "start_year", "count_of_issues")
    VOLUME_FIELD_LIST = ",".join(VOLUME_FIELDS)
    ISSUE_FIELD_LIST = ",".join(ISSUE_FIELDS)
    SEARCH_URL = BASE_URL + "search/?"
    ISSUE_ID_URL_TMPL = BASE_URL + f"issue/{ComicVineTypeID.ISSUE}-" + "{issue_id}/?"
    VOLUME_ID_URL_TMPL = (
        BASE_URL + f"volume/{ComicVineTypeID.VOLUME}-" + "{volume_id}/?"
    )

    ARTICLES = set(("the", "a", "and", "&", "issue"))
    NON_SEARCH_CHARS = (":", ",", "-")
    NON_SEARCH_CHARS_RE = regex.compile("|".join(NON_SEARCH_CHARS))
    VOLUME_CACHE = {}
    HEADERS = {"user-agent": f"comicbox/{VERSION}"}

    def __init__(self, api_key):
        self.api_key = api_key

    @classmethod
    def clean_query_string(cls, name):
        name = name.strip()
        name = cls.NON_SEARCH_CHARS_RE.sub("", name)
        name = name.lower()
        words = name.split(" ")
        query = ""
        for word in words:
            if word not in cls.ARTICLES:
                query = " ".join((query, word))

        return query, words

    def query_api(self, url, params, query):
        params.update({"api_key": self.api_key, "format": "json", "query": query})

        response = requests.get(url, headers=self.HEADERS, params=params)
        from pprint import pprint

        # pprint(response.url)
        # pprint(response.text)
        cv_response = response.json()
        pprint(cv_response)
        return cv_response

    def fetch_volume_by_id(self, cv_volume_id):
        cv_volume = self.VOLUME_CACHE.get(cv_volume_id)
        if cv_volume:
            return cv_volume

        url = self.VOLUME_ID_URL_TMPL.format(volume_id=cv_volume_id)
        params = {"field_list": self.VOLUME_FIELD_LIST}

        cv_response = self.query_api(url, params, None)
        cv_volume = cv_response.get("result")
        # TODO save to disk?
        self.VOLUME_CACHE[cv_volume_id] = cv_volume
        return cv_volume

    def fetch_issue_by_id(self, issue_id):
        url = self.ISSUE_ID_URL_TMPL.format(issue_id=issue_id)
        params = {"field_list": self.ISSUE_FIELD_LIST}
        cv_response = self.query_api(url, params, None)
        cv_issue = cv_response.get("results")

        cv_issue_volume = cv_issue.get("volume")
        cv_volume_id = cv_issue_volume.get("id")
        cv_volume = self.fetch_volume_by_id(cv_volume_id)

        cv_md = cv_issue
        # Replace the issue volume with the full volume
        cv_md["volume"] = cv_volume
        return cv_md

        # TODO unclear structure here were the network api adapter goes in relation to the
        # metadata parser because its multipart.

    def search(self, md):
        print(md)
        query_string = f"{md['series']} {md['volume']}"
        query, words = self.clean_query_string(query_string)
        cv_volume_id = self.VOLUME_CACHE.get(query)
        if cv_volume_id:
            # TODO fix
            return cv_volume_id
        params = {
            "field_list": self.VOLUME_FIELD_LIST,
            "resources": "volume",
            "page": 1,
        }
        cv_response = self.query_api(self.SEARCH_URL, params, query)
        search_results = cv_response.get("results")
        for index in range(len(search_results) - 1, 0, -1):
            result = search_results[index]
            self.VOLUME_CACHE[result.get("id")] = result
            name = result.get("name").lower()
            self.VOLUME_CACHE[name] = result
            for word in words:
                if word not in name and word != result.get("start_year"):
                    del search_results[index]
                    break

        from pprint import pprint

        pprint(search_results)

        return search_results

    def fetch_volume(self, series_id):
        params = {"field_list": self.VOLUME_FIELD_LIST}
        self.query_api(self.VOLUME_URL, params, None)

    def fetch_issues(self, series_ids=None, cover_date=None, issue_numbers=None):
        filter_list = []
        if series_ids:
            volume_list = "|".join(series_ids)
            filter_list += [f"volume:{volume_list}"]

        if cover_date is not None:
            filter_list += [f"cover_date:{cover_date}-1-1|{cover_date+1}-1-1"]

        if issue_numbers:
            issue_list = "|".join(issue_numbers)
            filter_list += [f"issue_number:{issue_list}"]

        params = {
            "field_list": self.ISSUE_FIELD_LIST,
        }
        if filter_list:
            params["filter"] = ",".join(filter_list)

        self.query_api(self.ISSUE_URL, params, None)

    def fetch_issue(self, series_id, issue_number):

        volume = self.fetch_volume(series_id)
        issues = self.fetch_issues([series_id], issue_numbers=None, cover_date=None)
        return volume, issues

    def search_issue(self, md):
        series_id = self.search_series(md.series_name)
        volume, issue = self.fetch_issue(series_id, md.issue_number)
        return volume, issue
