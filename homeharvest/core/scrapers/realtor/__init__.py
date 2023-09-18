import json
from ..models import Property, Address
from .. import Scraper
from typing import Any, Generator
from ....exceptions import NoResultsFound
from concurrent.futures import ThreadPoolExecutor, as_completed


class RealtorScraper(Scraper):
    def __init__(self, scraper_input):
        super().__init__(scraper_input)
        self.search_url = "https://www.realtor.com/api/v1/rdc_search_srp?client_id=rdc-search-new-communities&schema=vesta"

    def handle_location(self):
        headers = {
            "authority": "parser-external.geo.moveaws.com",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://www.realtor.com",
            "referer": "https://www.realtor.com/",
            "sec-ch-ua": '"Chromium";v="116", "Not)A;Brand";v="24", "Google Chrome";v="116"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        }

        params = {
            "input": self.location,
            "client_id": self.listing_type.value.replace('_', '-'),
            "limit": "1",
            "area_types": "city,state,county,postal_code,address,street,neighborhood,school,school_district,university,park",
        }

        response = self.session.get(
            "https://parser-external.geo.moveaws.com/suggest",
            params=params,
            headers=headers,
        )
        response_json = response.json()

        result = response_json["autocomplete"]

        if result is None:
            raise NoResultsFound("No results found for location: " + self.location)

        return result[0]

    def handle_address(self, property_id: str) -> list[Property]:
        query = """query Property($property_id: ID!) {
                    property(id: $property_id) {
                        property_id
                        details {
                            date_updated
                            garage
                            permalink
                            year_built
                            stories
                        }
                        address {
                            address_validation_code
                            city
                            country
                            county
                            line
                            postal_code
                            state_code
                            street_direction
                            street_name
                            street_number
                            street_suffix
                            street_post_direction
                            unit_value
                            unit
                            unit_descriptor
                            zip
                        }
                        basic {
                            baths
                            beds
                            price
                            sqft
                            lot_sqft
                            type
                            sold_price
                        }
                        public_record {
                            lot_size
                            sqft
                            stories
                            units
                            year_built
                        }
                    }
                }"""

        variables = {
            'property_id': property_id
        }

        payload = {
            'query': query,
            'variables': variables,
        }

        response = self.session.post(self.search_url, json=payload)
        response_json = response.json()

        property_info = response_json['data']['property']

        return [Property(
            site_name=self.site_name,
            address=Address(
                address_one=property_info['address']['line'],
                city=property_info['address']['city'],
                state=property_info['address']['state_code'],
                zip_code=property_info['address']['postal_code'],
            ),
            url="https://www.realtor.com/realestateandhomes-detail/" + property_info['details']['permalink'],
            beds=property_info['basic']['beds'],
            baths=property_info['basic']['baths'],
            stories=property_info['details']['stories'],
            year_built=property_info['details']['year_built'],
            square_feet=property_info['basic']['sqft'],
            price_per_square_foot=property_info['basic']['price'] / property_info['basic']['sqft']
            if property_info['basic']['sqft'] is not None and
            property_info['basic']['price'] is not None
            else None,
            price=property_info['basic']['price'],
            mls_id=property_id,
            listing_type=self.listing_type,
            lot_size=property_info['public_record']['lot_size'] if property_info['public_record'] is not None else None,
        )]

    def handle_area(self, variables: dict, return_total: bool = False) -> list[Property] | int:
        query = """query Home_search(
                            $city: String,
                            $county: [String],
                            $state_code: String,
                            $postal_code: String
                            $offset: Int,
                        ) {
                            home_search(
                                query: {
                                    city: $city
                                    county: $county
                                    postal_code: $postal_code
                                    state_code: $state_code
                                    status: %s
                                }
                                limit: 200
                                offset: $offset
                            ) {
                                count
                                total
                                results {
                                    property_id
                                    description {
                                        baths
                                        beds
                                        lot_sqft
                                        sqft
                                        text
                                        sold_price
                                        stories
                                        year_built
                                        garage
                                        unit_number
                                        floor_number
                                    }
                                    location {
                                        address {
                                            city
                                            country
                                            line
                                            postal_code
                                            state_code
                                            state
                                            street_direction
                                            street_name
                                            street_number
                                            street_post_direction
                                            street_suffix
                                            unit
                                        }
                                    }
                                    list_price
                                    price_per_sqft
                                    source {
                                        id
                                    }
                                }
                            }
                        }""" % self.listing_type.value

        payload = {
            'query': query,
            'variables': variables,
        }

        response = self.session.post(self.search_url, json=payload)
        response_json = response.json()

        if return_total:
            return response_json['data']['home_search']['total']

        properties: list[Property] = []

        for result in response_json['data']['home_search']['results']:
            realty_property = Property(
                address=Address(
                    address_one=result['location']['address']['line'],
                    city=result['location']['address']['city'],
                    state=result['location']['address']['state_code'],
                    zip_code=result['location']['address']['postal_code'],
                    address_two=result['location']['address']['unit'],
                ),
                site_name=self.site_name,
                url="https://www.realtor.com/realestateandhomes-detail/" + result['property_id'],
                beds=result['description']['beds'],
                baths=result['description']['baths'],
                stories=result['description']['stories'],
                year_built=result['description']['year_built'],
                square_feet=result['description']['sqft'],
                price_per_square_foot=result['price_per_sqft'],
                price=result['list_price'],
                mls_id=result['property_id'],
                listing_type=self.listing_type,
                lot_size=result['description']['lot_sqft'],
            )

            properties.append(realty_property)

        return properties

    def search(self):
        location_info = self.handle_location()
        location_type = location_info["area_type"]

        if location_type == 'address':
            property_id = location_info['mpr_id']
            return self.handle_address(property_id)

        offset = 0
        search_variables = {
            'city': location_info.get('city'),
            'county': location_info.get('county'),
            'state_code': location_info.get('state_code'),
            'postal_code': location_info.get('postal_code'),
            'offset': offset,
        }

        total = self.handle_area(search_variables, return_total=True)

        homes = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(
                    self.handle_area, variables=search_variables | {'offset': i}, return_total=False
                ) for i in range(0, total, 200)
            ]

            for future in as_completed(futures):
                homes.extend(future.result())

        return homes
