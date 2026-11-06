from pricescout.scrapers.robots import RobotsTxt

UA = "PriceScoutResearchBot/0.1 (educational project)"

ROBOTS = """
Sitemap: https://example.com/sitemap.xml

User-Agent: *
Disallow: /api/
Disallow: *de/list/*_*
Disallow: /*.pdf$
Allow: /api/public/
Crawl-delay: 2

User-agent: BadBot
User-agent: OtherBot
Disallow: /
"""


def test_wildcards_and_longest_match():
    r = RobotsTxt(ROBOTS)
    assert r.can_fetch(UA, "https://example.com/de/category/fernseher-203.html?page=2")
    assert not r.can_fetch(UA, "https://example.com/de/list/foo_bar")  # wildcard rule
    assert r.can_fetch(UA, "https://example.com/de/list/foobar")  # no underscore -> no match
    assert not r.can_fetch(UA, "https://example.com/api/private")
    assert r.can_fetch(UA, "https://example.com/api/public/x")  # longer Allow wins


def test_end_anchor():
    r = RobotsTxt(ROBOTS)
    assert not r.can_fetch(UA, "https://example.com/docs/manual.pdf")
    assert r.can_fetch(UA, "https://example.com/docs/manual.pdf?x=1")


def test_specific_group_and_shared_user_agent_lines():
    r = RobotsTxt(ROBOTS)
    assert not r.can_fetch("OtherBot/1.0", "https://example.com/anything")
    assert r.crawl_delay(UA) == 2


def test_empty_robots_allows_everything():
    assert RobotsTxt("").can_fetch(UA, "https://example.com/x")
