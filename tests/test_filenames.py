"""Test filenames with human parsed correct results."""

TEST_COMIC_FIELDS = {
    "series": "Long Series Name",
    "issue": "1",
    "year": 2000,
    "ext": "cbz",
}
TEST_COMIC_FIELDS_VOL = {
    "series": "Long Series Name",
    "volume": 1,
    "issue": "1",
    "year": 2000,
    "ext": "cbz",
}
TEST_COMIC_VOL_ONLY = {
    "series": "Long Series Name",
    "volume": 1,
    "year": 2000,
    "ext": "cbr",
}

FNS = {
    "Night of 1000 Wolves 001 (2013).cbz": {
        "series": "Night of 1000 Wolves",
        "issue": "1",
        "year": 2013,
        "ext": "cbz",
    },
    "19687 Sandman 53.cbz": {"series": "19687 Sandman", "issue": "53", "ext": "cbz"},
    "33475 OMAC v3 2.cbr": {
        "series": "33475 OMAC",
        "volume": 3,
        "issue": "2",
        "ext": "cbr",
    },
    "Long Series Name 001 (2000) Title (Source) (Releaser).cbz": TEST_COMIC_FIELDS,
    "Long Series Name #001 (2000) Title (Source) (Releaser).cbz": TEST_COMIC_FIELDS,
    "Long Series Name (2000) 001 Title (Source) (Releaser).cbz": TEST_COMIC_FIELDS,
    "Long Series Name (2000) #001 Title (Source) (Releaser).cbz": TEST_COMIC_FIELDS,
    "Long Series Name v1 (2000) #001 "
    "Title (Source) (Releaser).cbz": TEST_COMIC_FIELDS_VOL,
    "Long Series Name 001 (2000) (Source-Releaser).cbz": TEST_COMIC_FIELDS,
    "Long Series Name Vol 1 TPB "
    "(2000) (Source) (Releaser & Releaser-Releaser).cbr": TEST_COMIC_VOL_ONLY,
    "Ultimate Craziness (2019) (Digital) (Friends-of-Bill).cbr": {
        "series": "Ultimate Craziness",
        "year": 2019,
        "ext": "cbr",
    },
    "Jimmy Stocks Love Chain (2005) (digital) (The Magicians-Empire).cbr": {
        "series": "Jimmy Stocks Love Chain",
        "year": 2005,
        "ext": "cbr",
    },
    "Arkenstone Vol. 01 - The Smell of Burnt Toast (2020) (digital) (My-brother).cbr": {
        "series": "Arkenstone",
        "volume": 1,
        "year": 2020,
        "ext": "cbr",
    },
    "Bardude - The Last Thing I Remember.cbz": {
        "series": "Bardude The Last Thing I Remember",
        "ext": "cbz",
    },
    "Drunkguy - The Man Without Fear - 01.cbz": {
        "series": "Drunkguy The Man Without Fear",
        "issue": "1",
        "ext": "cbz",
    },
    "The_Arkenstone_v03_(2002)_(Digital)_(DR_&amp;_Quenya-Elves).cbr": {
        "series": "The Arkenstone",
        "volume": 3,
        "year": 2002,
        "ext": "cbr",
    },
    "Kartalk v01 001 - Fear the Brakes (2004) (digital) (Son of Ultron-EMpire).cbr": {
        "series": "Kartalk",
        "volume": 1,
        "issue": "1",
        "year": 2004,
        "ext": "cbr",
    },
    "Kartalk Library Edition v01 (1992) (digital) (Son of Ultron-Empire).cbr": {
        "series": "Kartalk Library Edition",
        "volume": 1,
        "year": 1992,
        "ext": "cbr",
    },
    "Kind of Deadly v02 - Last Bullet (2006) (Digital) (Zone-Empire).cbr": {
        "series": "Kind of Deadly",
        "volume": 2,
        "year": 2006,
        "ext": "cbr",
    },
    "Jeremy John - A Big Long Title (2017) (digital-Minutement).cbz": {
        "series": "Jeremy John A Big Long Title",
        "year": 2017,
        "ext": "cbz",
    },
    "Jeremy John 001 (2006) (digital (Minutemen-Faessla).cbz": {
        "series": "Jeremy John",
        "issue": "1",
        "year": 2006,
        "ext": "cbz",
    },
    "Jeremy John 003 (2007) (4 covers) (digital) (Minutemen-Faessla).cbz": {
        "series": "Jeremy John",
        "issue": "3",
        "year": 2007,
        "ext": "cbz",
    },
    "Jeremy John v01 - Uninterested! (2007) (Digital) (Asgard-Empire).cbr": {
        "series": "Jeremy John",
        "volume": 1,
        "year": 2007,
        "ext": "cbr",
    },
    "King of Skittles 01 (of 05) (2020) (digital) (Son of Ultron-Empire).cbr": {
        "series": "King of Skittles",
        "issue": "1",
        "issue_count": 5,
        "year": 2020,
        "ext": "cbr",
    },
    "Darkwad 011 (2019) (Digital) (Zone-Empire).cbr": {
        "series": "Darkwad",
        "issue": "11",
        "year": 2019,
        "ext": "cbr",
    },
    "Darkwad by Carlos Zemo v01 - Knuckle Fight (2009) (Digital) (Zone-Empire).cbr": {
        "series": "Darkwad by Carlos Zemo",
        "volume": 1,
        "year": 2009,
        "ext": "cbr",
    },
    "The Walking Dead #002 (2003).cbz": {
        "series": "The Walking Dead",
        "issue": "2",
        "year": 2003,
    },
    "The Walking Dead #3.cbz": {
        "series": "The Walking Dead",
        "issue": "3",
    },
    "The Walking Dead 4.cbz": {
        "series": "The Walking Dead",
        "issue": "4",
    },
    "A Fractional Comic 1.1.cbz": {"series": "A Fractional Comic", "issue": "1.1"},
    "A Fractional Comic 8.54.cbz": {"series": "A Fractional Comic", "issue": "8.54"},
    "Earth X #½.cbz": {"series": "Earth X", "issue": ".5"},
    "Avengers #001½.cbz": {"series": "Avengers", "issue": "1.5"},
    "The Amazing Spider-Man #78.BEY.cbz": {
        "series": "The Amazing Spider-Man",
        "issue": "78.BEY",
    },
    "The Amazing Spider-Man #54.LR.cbz": {
        "series": "The Amazing Spider-Man",
        "issue": "54.LR",
    },
    "Wolverine & the X-Men #27AU.cbz": {
        "series": "Wolverine & the X-Men",
        "issue": "27AU",
    },
    "Fantastic Four #5AU.cbz": {"series": "Fantastic Four", "issue": "5AU"},
}
