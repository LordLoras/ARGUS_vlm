/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SearchService {
    /**
     * Search Ads
     * @param q
     * @param mode
     * @param adId
     * @param promotion
     * @param k
     * @returns any Successful Response
     * @throws ApiError
     */
    public static searchAdsApiSearchGet(
        q?: (string | null),
        mode: 'keyword' | 'text' | 'visual' | 'hybrid' = 'hybrid',
        adId?: (string | null),
        promotion?: (string | null),
        k: number = 10,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/search',
            query: {
                'q': q,
                'mode': mode,
                'ad_id': adId,
                'promotion': promotion,
                'k': k,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
